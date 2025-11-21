#!/usr/bin/env python3
"""
run_testcase.py

Supports two modes:
    Practice (default): uses sample_tests.json (plain) with SAMPLE_* DB credentials.
    Evaluation (--zip): uses eval_tests.json.enc (encrypted) with EVAL_* DB credentials.
Encrypted evaluation tests are decrypted only in memory; test cases are never written in plaintext.

Usage:
    ./run_testcase solution.sql

Or:
    python run_testcase.py solution.sql
"""

import sys
from pathlib import Path
from typing import Dict
import re
import argparse
from shared.logger import get_logger

logger = get_logger(__name__)

try:
    from shared.sql_parser import parse_sql
    from shared.db_utils import get_db_connection
    from shared.constants import KEY_PATH
    from shared.encryption import get_or_create_key
    from shared.constants import (
        EVAL_TESTS_FILENAME,
        SAMPLE_TESTS_FILENAME,
        FieldNames,
        QueryType,
        ErrorMessages,
        REQUIRED_DB_FIELDS,
    )
    from shared.models import (
        DBConfig,
    )
    from student.test_utils import (
        pass_result as _pass_result,
        fail_result as _fail_result,
        error_result as _error_result,
        warning_result as _warning_result,
        missing_result as _missing_result,
        normalize_output as _normalize_output,
        compare_outputs as _compare_outputs,
        execute_query as _execute_query,
        print_test_header as _print_test_header,
        violates_constraints as _violates_constraints,
        load_and_decrypt_tests as _util_load_and_decrypt_tests,
        save_encrypted_report_and_zip as _util_save_encrypted_report_and_zip,
        print_results as _util_print_results,
    )
except ImportError as e:
    logger.error(f"Error importing modules: {e}")
    logger.error("Make sure required files are present.")
    sys.exit(1)


# Load or create encryption key from bundled data file
ENCRYPTION_KEY = get_or_create_key(KEY_PATH)


class TestRunner:
    """Runs tests against student solutions."""

    def __init__(self, tests_data: Dict, db_config: DBConfig):
        """
        Initialize test runner.

        Args:
            tests_data: Decrypted tests dictionary
            db_config: Database configuration dict (DBConfig type)
        """
        self.tests = tests_data
        self.db_config = db_config
        self.results = {}

    def test_select_query(
        self, test_key: str, test_data: Dict, student_query: str, conn
    ) -> Dict:
        """Test a SELECT query by comparing outputs."""
        instructor_query = test_data.get(FieldNames.QUERY, "")

        if not instructor_query:
            return _error_result(
                test_key,
                test_data,
                "No instructor query found in tests.json",
                student_query=student_query,
            )

        # Execute instructor's query
        success, result = _execute_query(instructor_query, conn)
        if not success:
            return _error_result(
                test_key,
                test_data,
                f"Instructor query execution error: {result}",
                student_query=student_query,
            )

        expected_output = _normalize_output(result)

        # Execute student query
        success, result = _execute_query(student_query, conn)
        if not success:
            return _error_result(
                test_key,
                test_data,
                f"Student query execution error: {result}",
                student_query=student_query,
            )

        # Compare outputs
        actual_output = _normalize_output(result)
        match, diff_msg = _compare_outputs(actual_output, expected_output)

        if match:
            return _pass_result(
                test_key,
                test_data,
                "Output matches expected result",
                student_query=student_query,
            )
        else:
            return _fail_result(
                test_key,
                test_data,
                f"Output mismatch: {diff_msg}",
                student_query=student_query,
                expected=expected_output,
                actual=actual_output,
            )

    def test_ddl_query(
        self, test_key: str, test_data: Dict, student_query: str, conn
    ) -> Dict:
        """Test DDL queries (CREATE TABLE, ALTER TABLE, etc.) using DESCRIBE."""
        _print_test_header(test_key, student_query)
        test_query = test_data.get(FieldNames.TEST_QUERY)
        expected_output = test_data.get(FieldNames.EXPECTED_OUTPUT, [])

        if not test_query:
            return _error_result(
                test_key, test_data, "No test_query defined for DDL test"
            )

        # Execute student's DDL query
        success, result = _execute_query(student_query, conn)
        if not success:
            return _error_result(test_key, test_data, f"DDL execution error: {result}")

        # Execute DESCRIBE query
        success, result = _execute_query(test_query, conn)
        if not success:
            return _error_result(test_key, test_data, f"DESCRIBE query error: {result}")

        # Compare structure
        actual_output = _normalize_output(result)
        match, diff_msg = _compare_outputs(actual_output, expected_output)

        if match:
            return _pass_result(test_key, test_data, "Table structure matches expected")
        else:
            return _fail_result(
                test_key,
                test_data,
                f"Table structure mismatch: {diff_msg}",
                expected=expected_output,
                actual=actual_output,
            )

    def test_view_query(
        self, test_key: str, test_data: Dict, student_query: str, conn
    ) -> Dict:
        """Test CREATE VIEW queries using DESCRIBE and optional validation query."""
        test_query = test_data.get(FieldNames.TEST_QUERY)
        expected_output = test_data.get(FieldNames.EXPECTED_OUTPUT, [])
        validation_query = test_data.get(FieldNames.VALIDATION_QUERY)
        validation_output = test_data.get(FieldNames.VALIDATION_OUTPUT, [])

        if not test_query:
            return _error_result(
                test_key,
                test_data,
                "No test_query defined for VIEW test",
                student_query=student_query,
            )

        # Execute student's CREATE VIEW query
        success, result = _execute_query(student_query, conn)
        if not success:
            return _error_result(
                test_key,
                test_data,
                f"VIEW creation error: {result}",
                student_query=student_query,
            )

        # Execute DESCRIBE query
        success, result = _execute_query(test_query, conn)
        if not success:
            return _error_result(
                test_key,
                test_data,
                f"DESCRIBE view error: {result}",
                student_query=student_query,
            )

        # Compare structure
        actual_output = _normalize_output(result)
        match, diff_msg = _compare_outputs(actual_output, expected_output)

        if not match:
            return _fail_result(
                test_key,
                test_data,
                f"View structure mismatch: {diff_msg}",
                student_query=student_query,
                expected=expected_output,
                actual=actual_output,
            )

        # If validation query is provided, also check the data
        if validation_query and validation_output:
            success, result = _execute_query(validation_query, conn)
            if not success:
                return _warning_result(
                    test_key,
                    test_data,
                    f"View structure OK but validation query failed: {result}",
                    0.5,
                    student_query=student_query,
                )

            actual_validation = _normalize_output(result)
            val_match, val_diff = _compare_outputs(actual_validation, validation_output)

            if not val_match:
                return _warning_result(
                    test_key,
                    test_data,
                    f"View structure OK but data mismatch: {val_diff}",
                    0.5,
                    student_query=student_query,
                )

        return _pass_result(
            test_key,
            test_data,
            "View created successfully and matches expected structure",
            student_query=student_query,
        )

    def test_function_query(
        self, test_key: str, test_data: Dict, student_query: str, conn
    ) -> Dict:
        """Test CREATE FUNCTION queries using function_tests."""
        function_tests = test_data.get(FieldNames.FUNCTION_TESTS, [])

        # Execute student's CREATE FUNCTION query
        success, result = _execute_query(student_query, conn)
        if not success:
            return _error_result(
                test_key,
                test_data,
                f"Function creation error: {result}",
                student_query=student_query,
            )

        if not function_tests:
            return _pass_result(
                test_key,
                test_data,
                "Function created successfully (no tests defined)",
                student_query=student_query,
            )

        # Run each function test
        failed_tests = []
        for idx, func_test in enumerate(function_tests):
            test_query = func_test.get(FieldNames.TEST_QUERY)
            expected_output = func_test.get(FieldNames.EXPECTED_OUTPUT, [])

            if not test_query:
                continue

            success, result = _execute_query(test_query, conn)
            if not success:
                failed_tests.append(f"Test {idx + 1}: Query error - {result}")
                continue

            actual_output = _normalize_output(result)
            match, diff_msg = _compare_outputs(actual_output, expected_output)
            if not match:
                failed_tests.append(f"Test {idx + 1}: {diff_msg}")

        if not failed_tests:
            return _pass_result(
                test_key,
                test_data,
                f"All {len(function_tests)} function tests passed",
                student_query=student_query,
            )
        else:
            return _fail_result(
                test_key,
                test_data,
                f"Failed {len(failed_tests)}/{len(function_tests)} tests",
                failures=failed_tests,
                student_query=student_query,
            )

    def test_dml_query(
        self, test_key: str, test_data: Dict, student_query: str, conn
    ) -> Dict:
        """Test DML queries (INSERT, UPDATE, DELETE) using validation query."""
        test_query = test_data.get(FieldNames.TEST_QUERY)
        expected_output = test_data.get(FieldNames.EXPECTED_OUTPUT, [])

        # Execute student's DML query
        success, result = _execute_query(student_query, conn)
        if not success:
            return _error_result(
                test_key,
                test_data,
                f"DML execution error: {result}",
                student_query=student_query,
            )

        if not test_query:
            return _pass_result(
                test_key,
                test_data,
                "DML executed successfully (no validation query)",
                student_query=student_query,
            )

        # Execute validation query
        success, result = _execute_query(test_query, conn)
        if not success:
            return _error_result(
                test_key,
                test_data,
                f"Validation query error: {result}",
                student_query=student_query,
            )

        # Compare results
        actual_output = _normalize_output(result)
        match, diff_msg = _compare_outputs(actual_output, expected_output)

        if match:
            return _pass_result(
                test_key,
                test_data,
                "DML result matches expected",
                student_query=student_query,
            )
        else:
            return _fail_result(
                test_key,
                test_data,
                f"Result mismatch: {diff_msg}",
                student_query=student_query,
                expected=expected_output,
                actual=actual_output,
            )

    def run_tests(self, solution_path: Path) -> Dict:
        """
        Run all tests against student solution.
        """
        # Load and parse student solution
        try:
            solution_sql = solution_path.read_text(encoding="utf-8")
        except Exception as e:
            return {
                "error": ErrorMessages.SOLUTION_READ_FAILED.format(error=e),
                FieldNames.TOTAL_SCORE: 0,
                FieldNames.MAX_SCORE: 0,
            }

        # Parse SQL queries
        try:
            parsed_queries = parse_sql(solution_sql)
        except Exception as e:
            return {
                "error": ErrorMessages.SOLUTION_PARSE_FAILED.format(error=e),
                FieldNames.TOTAL_SCORE: 0,
                FieldNames.MAX_SCORE: 0,
            }

        # Build a mapping of queries by index
        student_queries = {
            f"q{i + 1}": {
                FieldNames.QUERY: p.get(FieldNames.QUERY, ""),
                "type": p.get("type", "unknown"),
            }
            for i, p in enumerate(parsed_queries)
        }

        total_score = 0
        max_score = 0
        test_results = []

        # Connect to database using a context manager
        try:
            with get_db_connection(self.db_config) as conn:
                # Run tests for each query (sorted numerically)
                def sort_key(k):
                    match = re.search(r"\d+", k)
                    return int(match.group()) if match else 0

                # Filter out non-question keys (like _db_config)
                question_keys = [k for k in self.tests.keys() if k.startswith("q")]

                for test_key in sorted(question_keys, key=sort_key):
                    test_data = self.tests[test_key]
                    max_score += test_data.get(FieldNames.SCORE, 1)

                    if test_key not in student_queries:
                        result = _missing_result(
                            test_key,
                            test_data,
                            f"Student solution missing query {test_key}",
                        )
                        test_results.append(result)
                        continue

                    student_data = student_queries[test_key]
                    student_query = student_data[FieldNames.QUERY]
                    student_type = student_data.get("type", "unknown")
                    query_type = test_data.get(FieldNames.QUERY_TYPE, "").lower()

                    if (
                        not student_query
                        or not student_query.strip()
                        or student_type == "missing"
                    ):
                        result = _missing_result(
                            test_key, test_data, "Student did not answer (empty query)"
                        )
                        test_results.append(result)
                        continue

                    # Check constraints
                    violated = _violates_constraints(student_query, test_data)
                    if violated:
                        result = _fail_result(
                            test_key, test_data, f"Constraint violated: {violated}"
                        )
                        test_results.append(result)
                        continue

                    # Route to appropriate test method
                    if query_type == QueryType.SELECT:
                        result = self.test_select_query(
                            test_key, test_data, student_query, conn
                        )
                    elif query_type == QueryType.VIEW:
                        result = self.test_view_query(
                            test_key, test_data, student_query, conn
                        )
                    elif QueryType.TABLE in query_type or QueryType.DDL in query_type:
                        result = self.test_ddl_query(
                            test_key, test_data, student_query, conn
                        )
                    elif query_type == QueryType.FUNCTION:
                        result = self.test_function_query(
                            test_key, test_data, student_query, conn
                        )
                    elif query_type in [
                        QueryType.INSERT,
                        QueryType.UPDATE,
                        QueryType.DELETE,
                        QueryType.DML,
                    ]:
                        result = self.test_dml_query(
                            test_key, test_data, student_query, conn
                        )
                    else:
                        # Unknown type - try as select
                        result = self.test_select_query(
                            test_key, test_data, student_query, conn
                        )

                    test_results.append(result)
                    total_score += result.get(FieldNames.SCORE, 0)

        except Exception as e:
            return {
                "error": ErrorMessages.DB_CONNECTION_FAILED.format(error=e),
                FieldNames.TOTAL_SCORE: 0,
                FieldNames.MAX_SCORE: max_score,
                FieldNames.TEST_RESULTS: test_results,
            }

        return {
            FieldNames.TOTAL_SCORE: total_score,
            FieldNames.MAX_SCORE: max_score,
            "percentage": (total_score / max_score * 100) if max_score > 0 else 0,
            FieldNames.TEST_RESULTS: test_results,
        }


def main():
    """Main entry point with optional --zip packaging."""
    parser = argparse.ArgumentParser(description="Run SQL test cases.")
    parser.add_argument(
        "solution",
        nargs="?",
        default="solution.sql",
        help="Path to student solution.sql file (default: solution.sql)",
    )
    parser.add_argument(
        "--zip",
        metavar="STUDENT_ID",
        type=str,
        help="Run in evaluation mode with student ID (format: YYYY[A-Z][A-Z0-9][A-Z][A-Z0-9][0-9]{4}g). Uses eval_tests.json.enc and creates encrypted submission zip.",
    )
    args = parser.parse_args()

    # --- Mode and Path Setup (using pathlib) ---
    eval_mode = args.zip is not None
    student_id = ""

    # Use Path.cwd() as the base for all relative paths
    cwd = Path.cwd()
    solution_path = Path(args.solution)
    if not solution_path.is_absolute():
        solution_path = cwd / solution_path

    # Validate student_id if in eval mode
    if eval_mode:
        student_id = args.zip.strip().lower()
        if not student_id:
            logger.error("Error: Student ID is required when using --zip")
            logger.error("Usage: ./run_testcase --zip <student_id>")
            logger.error("Example: ./run_testcase --zip 2021a7ps0001g")
            sys.exit(2)

        if not re.fullmatch(
            r"\d{4}[a-z][a-z0-9][a-z][a-z0-9]\d{4}g", student_id, flags=re.I
        ):
            logger.error(
                "Error: Invalid student ID format. Expected YYYY[A-Z][A-Z0-9][A-Z][A-Z0-9][0-9]{4}g"
            )
            logger.error("Example: 2021a7ps0001g")
            sys.exit(2)

    # --- Load Test Data ---
    if not solution_path.exists():
        logger.error(ErrorMessages.SOLUTION_NOT_FOUND.format(path=solution_path))
        sys.exit(1)

    try:
        if eval_mode:
            test_file_name = EVAL_TESTS_FILENAME
        else:
            test_file_name = SAMPLE_TESTS_FILENAME

        tests_path = cwd / test_file_name
        if not tests_path.exists():
            logger.error(ErrorMessages.TESTS_NOT_FOUND.format(path=tests_path))
            sys.exit(1)
        logger.info("Loading encrypted tests...")
        tests_data = _util_load_and_decrypt_tests(tests_path, ENCRYPTION_KEY)
    except Exception as e:
        logger.error(ErrorMessages.TESTS_LOAD_FAILED.format(error=e))
        sys.exit(1)

    logger.info("Tests loaded successfully. Running validation...")

    # --- Extract DB Config from Test JSON ---
    db_config_data = tests_data.get(FieldNames.DB_CONFIG)
    if not db_config_data:
        logger.error(ErrorMessages.DB_CONFIG_NOT_FOUND)
        sys.exit(1)

    # Validate DB config has required fields
    for field in REQUIRED_DB_FIELDS:
        if field not in db_config_data:
            logger.error(ErrorMessages.DB_FIELD_MISSING.format(field=field))
            sys.exit(1)

    db_config = db_config_data

    # --- Run and Print ---
    runner = TestRunner(tests_data, db_config)
    results = runner.run_tests(solution_path)
    _util_print_results(results)

    if eval_mode:
        _util_save_encrypted_report_and_zip(
            results, solution_path, student_id, ENCRYPTION_KEY
        )
    else:
        logger.info(
            "(Skipping report save; run with --zip to generate encrypted results and ZIP.)"
        )

    # --- Exit Status ---
    if "error" in results:
        sys.exit(1)
    elif results.get(FieldNames.TOTAL_SCORE, 0) < results.get(FieldNames.MAX_SCORE, 1):
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
