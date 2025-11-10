#!/usr/bin/env python3
"""
run_testcase.py

Supports two modes:
    Practice (default): uses sample_tests.json (plain) with SAMPLE_* DB credentials.
    Evaluation (--zip): uses eval_tests.json.enc (encrypted) with EVAL_* DB credentials; time gating enforced if tests specify allowed_after.
Encrypted evaluation tests are decrypted only in memory; test cases are never written in plaintext.

Usage:
    ./run_testcase solution.sql

Or:
    python run_testcase.py solution.sql
"""
import sys
import os
import json
import tempfile
from typing import Dict, List, Any, Tuple
import re
import argparse
import zipfile

# ENCRYPTION KEY - SET BY INSTRUCTOR BEFORE DISTRIBUTION
ENCRYPTION_KEY = b"nVPZZCjg6EFcWrch2Ivk13WWXNv7uWZGU5C5Vc2ADrw="  # Set automatically by build process

# Import local modules
try:
    from sql_parser import parse_sql
    from db_utils import get_db_connection
    from config import get_db_config, load_env_file
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure required files are present.")
    sys.exit(1)

try:
    import pymysql
except ImportError:
    print("Error: PyMySQL not installed. Please install it with:")
    print("    pip install pymysql")
    sys.exit(1)

try:
    from cryptography.fernet import Fernet

    CRYPTO_AVAILABLE = True
except ImportError:
    print("Error: cryptography library not installed.")
    print("    pip install cryptography")
    CRYPTO_AVAILABLE = False
    sys.exit(1)


class TestRunner:
    """Runs tests against student solutions."""

    def __init__(self, tests_data: Dict, db_config: Dict):
        """
        Initialize test runner.

        Args:
            tests_data: Decrypted tests dictionary
            db_config: Database configuration dict
        """
        self.tests = tests_data
        self.db_config = db_config
        self.results = {}

    def _load_and_decrypt_tests(encrypted_path: str) -> Dict:
        """
        Load and decrypt eval_tests.json.enc file.

            Args:
                encrypted_path: Path to eval_tests.json.enc

            Returns:
                Decrypted tests dictionary

            Raises:
                Exception if decryption fails
        """
        if not ENCRYPTION_KEY or ENCRYPTION_KEY == b"":
            raise Exception("Encryption key not set. Contact instructor.")

        if not CRYPTO_AVAILABLE:
            raise Exception("Cryptography library not available.")

        try:
            # Read encrypted file
            with open(encrypted_path, "rb") as f:
                encrypted_data = f.read()

            # Decrypt
            fernet = Fernet(ENCRYPTION_KEY)
            decrypted_data = fernet.decrypt(encrypted_data)

            # Parse JSON
            tests = json.loads(decrypted_data.decode("utf-8"))

            return tests

        except Exception as e:
            raise Exception(f"Failed to decrypt tests: {e}")

    def _normalize_output(self, rows: List[tuple]) -> List[List[str]]:
        """
        Normalize query output to list of string lists for comparison.

        Args:
            rows: List of tuples from database query

        Returns:
            List of lists with all values converted to strings
        """
        return [[str(cell) if cell is not None else "" for cell in row] for row in rows]

    def _compare_outputs(
        self, actual: List[List[str]], expected: List[List[str]]
    ) -> Tuple[bool, str]:
        """
        Compare actual output with expected output.

        Args:
            actual: Actual query results
            expected: Expected query results

        Returns:
            Tuple of (is_match, difference_message)
        """
        if len(actual) != len(expected):
            return (
                False,
                f"Row count mismatch: expected {len(expected)}, got {len(actual)}",
            )

        for i, (actual_row, expected_row) in enumerate(zip(actual, expected)):
            if len(actual_row) != len(expected_row):
                return (
                    False,
                    f"Column count mismatch at row {i+1}: expected {len(expected_row)}, got {len(actual_row)}",
                )

            for j, (actual_val, expected_val) in enumerate(
                zip(actual_row, expected_row)
            ):
                # Try numeric comparison first for floating point tolerance
                try:
                    actual_num = float(actual_val)
                    expected_num = float(expected_val)
                    if abs(actual_num - expected_num) > 1e-6:
                        return (
                            False,
                            f"Value mismatch at row {i+1}, col {j+1}: expected '{expected_val}', got '{actual_val}'",
                        )
                except (ValueError, TypeError):
                    # String comparison
                    if str(actual_val) != str(expected_val):
                        return (
                            False,
                            f"Value mismatch at row {i+1}, col {j+1}: expected '{expected_val}', got '{actual_val}'",
                        )

        return (True, "")

    def _execute_query(self, query: str, conn) -> Tuple[bool, Any]:
        """
        Execute a query and return results.

        Args:
            query: SQL query to execute
            conn: Database connection

        Returns:
            Tuple of (success, results_or_error)
        """
        try:
            cursor = conn.cursor()
            cursor.execute(query)
            results = cursor.fetchall()
            cursor.close()
            return (True, results)
        except Exception as e:
            return (False, str(e))

    def test_select_query(
        self, test_key: str, test_data: Dict, student_query: str, conn
    ) -> Dict:
        """
        Test a SELECT query by comparing outputs.

        Executes both the instructor's query (from tests.json) and the student's query,
        then compares their outputs.

        Args:
            test_key: Test identifier (e.g., "q1")
            test_data: Test data from tests.json (contains instructor's query)
            student_query: Student's SQL query
            conn: Database connection

        Returns:
            Dict with test results
        """
        # Print query being tested
        print(f"\nTesting {test_key}:")
        print(
            f"Query: {student_query[:200]}{'...' if len(student_query) > 200 else ''}"
        )
        print("-" * 60)

        # Get instructor's query from tests.json
        instructor_query = test_data.get("query", "")

        if not instructor_query:
            return {
                "test": test_key,
                "status": "ERROR",
                "message": "No instructor query found in tests.json",
                "score": 0,
                "max_score": test_data.get("score", 1),
            }

        # Execute instructor's query to get expected output
        success, result = self._execute_query(instructor_query, conn)
        if not success:
            return {
                "test": test_key,
                "status": "ERROR",
                "message": f"Instructor query execution error: {result}",
                "score": 0,
                "max_score": test_data.get("score", 1),
            }

        expected_output = self._normalize_output(result)

        # Execute student query
        success, result = self._execute_query(student_query, conn)
        if not success:
            return {
                "test": test_key,
                "status": "ERROR",
                "message": f"Student query execution error: {result}",
                "score": 0,
                "max_score": test_data.get("score", 1),
            }

        # Compare outputs
        actual_output = self._normalize_output(result)
        match, diff_msg = self._compare_outputs(actual_output, expected_output)

        if match:
            return {
                "test": test_key,
                "status": "PASS",
                "message": "Output matches expected result",
                "score": test_data.get("score", 1),
                "max_score": test_data.get("score", 1),
            }
        else:
            return {
                "test": test_key,
                "status": "FAIL",
                "message": f"Output mismatch: {diff_msg}",
                "score": 0,
                "max_score": test_data.get("score", 1),
                "expected": expected_output,
                "actual": actual_output,
            }

    def test_ddl_query(
        self, test_key: str, test_data: Dict, student_query: str, conn
    ) -> Dict:
        """
        Test DDL queries (CREATE TABLE, ALTER TABLE, etc.) using DESCRIBE.

        Args:
            test_key: Test identifier
            test_data: Test data from tests.json with test_query (DESCRIBE)
            student_query: Student's DDL query
            conn: Database connection

        Returns:
            Dict with test results
        """
        # Print query being tested
        print(f"\nTesting {test_key}:")
        print(
            f"Query: {student_query[:200]}{'...' if len(student_query) > 200 else ''}"
        )
        print("-" * 60)

        test_query = test_data.get("test_query")
        expected_output = test_data.get("expected_output", [])

        if not test_query:
            return {
                "test": test_key,
                "status": "ERROR",
                "message": "No test_query defined for DDL test",
                "score": 0,
                "max_score": test_data.get("score", 1),
            }

        # Execute student's DDL query
        success, result = self._execute_query(student_query, conn)
        if not success:
            return {
                "test": test_key,
                "status": "ERROR",
                "message": f"DDL execution error: {result}",
                "score": 0,
                "max_score": test_data.get("score", 1),
            }

        # Execute DESCRIBE query to check table structure
        success, result = self._execute_query(test_query, conn)
        if not success:
            return {
                "test": test_key,
                "status": "ERROR",
                "message": f"DESCRIBE query error: {result}",
                "score": 0,
                "max_score": test_data.get("score", 1),
            }

        # Compare structure
        actual_output = self._normalize_output(result)
        match, diff_msg = self._compare_outputs(actual_output, expected_output)

        if match:
            return {
                "test": test_key,
                "status": "PASS",
                "message": "Table structure matches expected",
                "score": test_data.get("score", 1),
                "max_score": test_data.get("score", 1),
            }
        else:
            return {
                "test": test_key,
                "status": "FAIL",
                "message": f"Table structure mismatch: {diff_msg}",
                "score": 0,
                "max_score": test_data.get("score", 1),
                "expected": expected_output,
                "actual": actual_output,
            }

    def test_view_query(
        self, test_key: str, test_data: Dict, student_query: str, conn
    ) -> Dict:
        """
        Test CREATE VIEW queries using DESCRIBE and optional validation query.

        Args:
            test_key: Test identifier
            test_data: Test data from tests.json with test_query (DESCRIBE) and validation_query
            student_query: Student's CREATE VIEW query
            conn: Database connection

        Returns:
            Dict with test results
        """
        # Print query being tested
        print(f"\nTesting {test_key}:")
        print(
            f"Query: {student_query[:200]}{'...' if len(student_query) > 200 else ''}"
        )
        print("-" * 60)

        test_query = test_data.get("test_query")
        expected_output = test_data.get("expected_output", [])
        validation_query = test_data.get("validation_query")
        validation_output = test_data.get("validation_output", [])

        if not test_query:
            return {
                "test": test_key,
                "status": "ERROR",
                "message": "No test_query defined for VIEW test",
                "score": 0,
                "max_score": test_data.get("score", 1),
            }

        # Execute student's CREATE VIEW query
        success, result = self._execute_query(student_query, conn)
        if not success:
            return {
                "test": test_key,
                "status": "ERROR",
                "message": f"VIEW creation error: {result}",
                "score": 0,
                "max_score": test_data.get("score", 1),
            }

        # Execute DESCRIBE query to check view structure
        success, result = self._execute_query(test_query, conn)
        if not success:
            return {
                "test": test_key,
                "status": "ERROR",
                "message": f"DESCRIBE view error: {result}",
                "score": 0,
                "max_score": test_data.get("score", 1),
            }

        # Compare structure
        actual_output = self._normalize_output(result)
        match, diff_msg = self._compare_outputs(actual_output, expected_output)

        if not match:
            return {
                "test": test_key,
                "status": "FAIL",
                "message": f"View structure mismatch: {diff_msg}",
                "score": 0,
                "max_score": test_data.get("score", 1),
                "expected": expected_output,
                "actual": actual_output,
            }

        # If validation query is provided, also check the data
        if validation_query and validation_output:
            success, result = self._execute_query(validation_query, conn)
            if not success:
                return {
                    "test": test_key,
                    "status": "WARNING",
                    "message": f"View structure OK but validation query failed: {result}",
                    "score": test_data.get("score", 1) * 0.5,  # Partial credit
                    "max_score": test_data.get("score", 1),
                }

            actual_validation = self._normalize_output(result)
            val_match, val_diff = self._compare_outputs(
                actual_validation, validation_output
            )

            if not val_match:
                return {
                    "test": test_key,
                    "status": "WARNING",
                    "message": f"View structure OK but data mismatch: {val_diff}",
                    "score": test_data.get("score", 1) * 0.5,  # Partial credit
                    "max_score": test_data.get("score", 1),
                }

        return {
            "test": test_key,
            "status": "PASS",
            "message": "View created successfully and matches expected structure",
            "score": test_data.get("score", 1),
            "max_score": test_data.get("score", 1),
        }

    def test_function_query(
        self, test_key: str, test_data: Dict, student_query: str, conn
    ) -> Dict:
        """
        Test CREATE FUNCTION queries using function_tests.

        Args:
            test_key: Test identifier
            test_data: Test data from tests.json with function_tests
            student_query: Student's CREATE FUNCTION query
            conn: Database connection

        Returns:
            Dict with test results
        """
        # Print query being tested
        print(f"\nTesting {test_key}:")
        print(
            f"Query: {student_query[:200]}{'...' if len(student_query) > 200 else ''}"
        )
        print("-" * 60)

        function_tests = test_data.get("function_tests", [])

        # Execute student's CREATE FUNCTION query
        success, result = self._execute_query(student_query, conn)
        if not success:
            return {
                "test": test_key,
                "status": "ERROR",
                "message": f"Function creation error: {result}",
                "score": 0,
                "max_score": test_data.get("score", 1),
            }

        if not function_tests:
            return {
                "test": test_key,
                "status": "PASS",
                "message": "Function created successfully (no tests defined)",
                "score": test_data.get("score", 1),
                "max_score": test_data.get("score", 1),
            }

        # Run each function test
        failed_tests = []
        for idx, func_test in enumerate(function_tests):
            test_query = func_test.get("test_query")
            expected_output = func_test.get("expected_output", [])

            if not test_query:
                continue

            success, result = self._execute_query(test_query, conn)
            if not success:
                failed_tests.append(f"Test {idx+1}: Query error - {result}")
                continue

            actual_output = self._normalize_output(result)
            match, diff_msg = self._compare_outputs(actual_output, expected_output)
            if not match:
                failed_tests.append(f"Test {idx+1}: {diff_msg}")

        if not failed_tests:
            return {
                "test": test_key,
                "status": "PASS",
                "message": f"All {len(function_tests)} function tests passed",
                "score": test_data.get("score", 1),
                "max_score": test_data.get("score", 1),
            }
        else:
            return {
                "test": test_key,
                "status": "FAIL",
                "message": f"Failed {len(failed_tests)}/{len(function_tests)} tests",
                "failures": failed_tests,
                "score": 0,
                "max_score": test_data.get("score", 1),
            }

    def test_dml_query(
        self, test_key: str, test_data: Dict, student_query: str, conn
    ) -> Dict:
        """
        Test DML queries (INSERT, UPDATE, DELETE) using validation query.

        Args:
            test_key: Test identifier
            test_data: Test data from tests.json with test_query for validation
            student_query: Student's DML query
            conn: Database connection

        Returns:
            Dict with test results
        """
        # Print query being tested
        print(f"\nTesting {test_key}:")
        print(
            f"Query: {student_query[:200]}{'...' if len(student_query) > 200 else ''}"
        )
        print("-" * 60)

        test_query = test_data.get("test_query")
        expected_output = test_data.get("expected_output", [])

        # Execute student's DML query
        success, result = self._execute_query(student_query, conn)
        if not success:
            return {
                "test": test_key,
                "status": "ERROR",
                "message": f"DML execution error: {result}",
                "score": 0,
                "max_score": test_data.get("score", 1),
            }

        if not test_query:
            return {
                "test": test_key,
                "status": "PASS",
                "message": "DML executed successfully (no validation query)",
                "score": test_data.get("score", 1),
                "max_score": test_data.get("score", 1),
            }

        # Execute validation query
        success, result = self._execute_query(test_query, conn)
        if not success:
            return {
                "test": test_key,
                "status": "ERROR",
                "message": f"Validation query error: {result}",
                "score": 0,
                "max_score": test_data.get("score", 1),
            }

        # Compare results
        actual_output = self._normalize_output(result)
        match, diff_msg = self._compare_outputs(actual_output, expected_output)

        if match:
            return {
                "test": test_key,
                "status": "PASS",
                "message": "DML result matches expected",
                "score": test_data.get("score", 1),
                "max_score": test_data.get("score", 1),
            }
        else:
            return {
                "test": test_key,
                "status": "FAIL",
                "message": f"Result mismatch: {diff_msg}",
                "score": 0,
                "max_score": test_data.get("score", 1),
                "expected": expected_output,
                "actual": actual_output,
            }

    def violates_constraints(self, student_query: str, test: dict) -> str:
        q = student_query.lower()
        # forbid_join: fail if join is present
        if test.get("forbid_join") and "join" in q:
            return "forbid_join"
        # require_join: fail if join is missing
        if test.get("require_join") and "join" not in q:
            return "require_join"
        # require_nested_select: fail if subquery not present (simple regex)
        if test.get("require_nested_select") and not re.search(
            r"\([ \t\n\r]*select", q, re.I
        ):
            return "require_nested_select"
        # forbid_nested_select: fail if subquery present
        if test.get("forbid_nested_select") and re.search(
            r"\([ \t\n\r]*select", q, re.I
        ):
            return "forbid_nested_select"
        if test.get("forbid_group_by") and "group by" in q:
            return "forbid_group_by"
        if test.get("require_group_by") and "group by" not in q:
            return "require_group_by"
        if test.get("forbid_order_by") and "order by" in q:
            return "forbid_order_by"
        if test.get("require_order_by") and "order by" not in q:
            return "require_order_by"
        return ""

    def run_tests(self, solution_path: str) -> Dict:
        """
        Run all tests against student solution.

        Args:
            solution_path: Path to student's solution.sql file

        Returns:
            Dict with complete test results
        """
        # Load and parse student solution
        try:
            with open(solution_path, "r", encoding="utf-8") as f:
                solution_sql = f.read()
        except Exception as e:
            return {
                "error": f"Failed to read solution file: {e}",
                "total_score": 0,
                "max_score": 0,
            }

        # Parse SQL queries
        try:
            parsed_queries = parse_sql(solution_sql)
        except Exception as e:
            return {
                "error": f"Failed to parse solution SQL: {e}",
                "total_score": 0,
                "max_score": 0,
            }

        # Build a mapping of queries by index
        student_queries = {}
        for i, parsed in enumerate(parsed_queries, start=1):
            query_key = f"q{i}"
            student_queries[query_key] = {
                "query": parsed.get("query", ""),
                "type": parsed.get("type", "unknown"),
            }

        # Connect to database
        try:
            conn = get_db_connection(self.db_config)
        except Exception as e:
            return {
                "error": f"Failed to connect to database: {e}",
                "total_score": 0,
                "max_score": 0,
            }

        total_score = 0
        max_score = 0
        test_results = []

        try:
            # Run tests for each query (sorted numerically)
            def sort_key(k):
                # Extract number from key like "q1", "q2", "q10"
                match = re.search(r"\d+", k)
                return int(match.group()) if match else 0

            for test_key in sorted(self.tests.keys(), key=sort_key):
                test_data = self.tests[test_key]
                max_score += test_data.get("score", 1)

                # Check if student provided this query
                if test_key not in student_queries:
                    test_results.append(
                        {
                            "test": test_key,
                            "status": "MISSING",
                            "message": f"Student solution missing query {test_key}",
                            "score": 0,
                            "max_score": test_data.get("score", 1),
                        }
                    )
                    continue

                student_data = student_queries[test_key]
                student_query = student_data["query"]
                student_type = student_data.get("type", "unknown")
                query_type = test_data.get("query_type", "").lower()

                # Check if student wrote empty query (just ";")
                if (
                    not student_query
                    or not student_query.strip()
                    or student_type == "missing"
                ):
                    test_results.append(
                        {
                            "test": test_key,
                            "status": "MISSING",
                            "message": "Student did not answer this question (empty query or just semicolon)",
                            "score": 0,
                            "max_score": test_data.get("score", 1),
                        }
                    )
                    continue

                # Check constraints
                violated = self.violates_constraints(student_query, test_data)
                if violated:
                    test_results.append(
                        {
                            "test": test_key,
                            "status": "FAIL",
                            "message": f"Constraint violated: {violated}",
                            "score": 0,
                            "max_score": 1,
                            "expected": None,
                            "actual": None,
                        }
                    )
                    continue

                # Route to appropriate test method
                if query_type == "select":
                    result = self.test_select_query(
                        test_key, test_data, student_query, conn
                    )
                elif query_type == "view":
                    result = self.test_view_query(
                        test_key, test_data, student_query, conn
                    )
                elif "table" in query_type or "ddl" in query_type:
                    result = self.test_ddl_query(
                        test_key, test_data, student_query, conn
                    )
                elif query_type == "function":
                    result = self.test_function_query(
                        test_key, test_data, student_query, conn
                    )
                elif query_type in ["insert", "update", "delete", "dml"]:
                    result = self.test_dml_query(
                        test_key, test_data, student_query, conn
                    )
                else:
                    # Unknown type - try as select
                    result = self.test_select_query(
                        test_key, test_data, student_query, conn
                    )

                test_results.append(result)
                total_score += result.get("score", 0)

        finally:
            conn.close()

        return {
            "total_score": total_score,
            "max_score": max_score,
            "percentage": (total_score / max_score * 100) if max_score > 0 else 0,
            "test_results": test_results,
        }


def print_results(results: Dict):
    """Print test results in a readable format."""
    import sys

    def supports_color():
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    GREEN = "\033[92m" if supports_color() else ""
    RED = "\033[91m" if supports_color() else ""
    YELLOW = "\033[93m" if supports_color() else ""
    RESET = "\033[0m" if supports_color() else ""

    print("\n" + "=" * 70)
    print("TEST RESULTS")
    print("=" * 70)

    if "error" in results:
        print(f"\n{RED}ERROR: {results['error']}{RESET}")
        return

    test_results = results.get("test_results", [])
    for result in test_results:
        test_key = result.get("test", "unknown")
        status = result.get("status", "UNKNOWN")
        message = result.get("message", "")
        score = result.get("score", 0)
        max_score = result.get("max_score", 1)
        # Status indicator + color
        if status == "PASS":
            indicator = f"{GREEN}✓{RESET}"
            status_line = f"{GREEN}{status}{RESET}"
        elif status == "FAIL":
            indicator = f"{RED}✗{RESET}"
            status_line = f"{RED}{status}{RESET}"
        elif status == "ERROR":
            indicator = f"{YELLOW}⚠{RESET}"
            status_line = f"{YELLOW}{status}{RESET}"
        else:
            indicator = "?"
            status_line = status
        print(f"\n{indicator} {test_key}: {status_line} ({score}/{max_score} points)")
        print(f"   {message}")
        # Print failures for function tests
        if "failures" in result:
            for failure in result["failures"]:
                print(f"     - {failure}")
        # Print expected vs actual for mismatches
        if status == "FAIL" and "expected" in result and "actual" in result:
            print(f"   Expected: {result['expected']}")
            print(f"   Actual:   {result['actual']}")
    print("\n" + "=" * 70)
    print(
        f"FINAL SCORE: {GREEN if results['total_score']==results['max_score'] else RED}{results['total_score']}{RESET}/{results['max_score']} ({results['percentage']:.2f}%){RESET}"
    )
    print("=" * 70 + "\n")


def save_encrypted_report_and_zip(results: Dict, solution_path: str, student_id: str):
    """When --zip is used: create encrypted results.json.enc and submission zip."""
    from datetime import datetime

    # Prepare metadata
    results_with_metadata = {
        "student_id": student_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **results,
    }

    # Build minimal encrypted payload: student_id, timestamp, q1..qN => Pass or reason, total_score
    encrypted_report_path = os.path.join(os.getcwd(), f"{student_id}_results.json.enc")
    try:
        if CRYPTO_AVAILABLE and ENCRYPTION_KEY:
            # Construct minimal results schema
            # questions map: qN -> "Pass" or failure reason
            questions = {}
            for tr in results.get("test_results", []):
                qid = tr.get("test") or ""
                status = tr.get("status", "")
                msg = tr.get("message", "")
                questions[qid] = (
                    "Pass" if status == "PASS" else (msg or status or "FAIL")
                )

            minimal_payload = {
                "student_id": results_with_metadata.get("student_id", ""),
                "timestamp": results_with_metadata.get("timestamp", ""),
                "total_score": results.get("total_score", 0),
                "questions": questions,
            }

            fernet = Fernet(ENCRYPTION_KEY)
            encrypted_data = fernet.encrypt(
                json.dumps(minimal_payload, indent=2).encode("utf-8")
            )
            with open(encrypted_report_path, "wb") as f:
                f.write(encrypted_data)
            print(f"Encrypted results saved: {encrypted_report_path}")
        else:
            print("Skipping encryption: cryptography or key unavailable.")
            return
    except Exception as e:
        print(f"Failed to create encrypted results: {e}")
        return

    # Create ZIP containing solution.sql and encrypted results
    zip_path = os.path.join(os.getcwd(), f"{student_id}_submission.zip")
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # add solution
            if os.path.exists(solution_path):
                zf.write(solution_path, arcname="solution.sql")
            # add encrypted results
            if os.path.exists(encrypted_report_path):
                zf.write(encrypted_report_path, arcname=encrypted_report_path)
        print(f"Submission ZIP created: {zip_path}")
        print(f"Files inside: solution.sql, {encrypted_report_path}")
    except Exception as e:
        print(f"Failed to create submission zip: {e}")


def main():
    """Main entry point with optional --zip packaging.

    Practice mode (default): uses sample_tests.json and SAMPLE_* DB env vars.
    Evaluation mode (--zip): uses eval_tests.json.enc and EVAL_* DB env vars, then saves encrypted results and ZIP.
    """
    parser = argparse.ArgumentParser(description="Run SQL test cases.")
    parser.add_argument(
        "solution",
        nargs="?",
        default="solution.sql",
        help="Path to student solution.sql file (default: solution.sql)",
    )
    parser.add_argument(
        "--zip",
        action="store_true",
        help="After running tests, create results.json.enc and submission.zip (solution.sql + results.json.enc).",
    )
    parser.add_argument(
        "--student-id",
        dest="student_id",
        help="Student ID required with --zip (format: YYYY[A-Z][A-Z0-9][A-Z][A-Z0-9][0-9]{4}g)",
    )
    args = parser.parse_args()
    # If packaging is requested, validate student_id
    if args.zip:
        sid = (args.student_id or "").strip()
        if not sid:
            print("Error: --student-id is required when using --zip")
            sys.exit(2)
        # Validate pattern: 4 digits, L, L/D, L, L/D, 4 digits, 'g' (case-insensitive)
        sid_norm = sid.lower()
        if not re.fullmatch(
            r"\d{4}[a-z][a-z0-9][a-z][a-z0-9]\d{4}g", sid_norm, flags=re.I
        ):
            print(
                "Error: Invalid student ID format. Expected YYYY[A-Z][A-Z0-9][A-Z][A-Z0-9][0-9]{4}g (e.g., 2022b3a70031g)"
            )
            sys.exit(2)
        args.student_id = sid_norm

    solution_path = args.solution
    eval_mode = args.zip is True
    tests_enc_path = "eval_tests.json.enc"
    sample_tests_path = "sample_tests.json"

    # Make paths absolute if relative
    if not os.path.isabs(solution_path):
        solution_path = os.path.join(os.getcwd(), solution_path)
    if eval_mode and not os.path.isabs(tests_enc_path):
        tests_enc_path = os.path.join(os.getcwd(), tests_enc_path)
    if (not eval_mode) and not os.path.isabs(sample_tests_path):
        sample_tests_path = os.path.join(os.getcwd(), sample_tests_path)

    if not os.path.exists(solution_path):
        print(f"Error: Solution file not found: {solution_path}")
        sys.exit(1)
    if eval_mode:
        if not os.path.exists(tests_enc_path):
            print(f"Error: Encrypted evaluation tests file not found: {tests_enc_path}")
            sys.exit(1)
    else:
        if not os.path.exists(sample_tests_path):
            print(f"Error: Sample tests file not found: {sample_tests_path}")
            sys.exit(1)

    print(f"Testing solution: {solution_path}")
    if eval_mode:
        print("Loading encrypted evaluation tests...")
        try:
            tests_data = TestRunner._load_and_decrypt_tests(tests_enc_path)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        print("Loading sample tests...")
        try:
            with open(sample_tests_path, "r", encoding="utf-8") as f:
                tests_data = json.load(f)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

    # Enforce time gate only in eval mode (if provided in tests)
    if eval_mode:
        first_test = (
            next(iter(tests_data.values()), {}) if isinstance(tests_data, dict) else {}
        )
        allowed_after = first_test.get("allowed_after")
        if allowed_after:
            # Convert current UTC time to IST (Asia/Kolkata) reliably.
            from datetime import datetime, timedelta, time as dtime

            try:
                try:
                    from zoneinfo import ZoneInfo  # Python 3.9+

                    ist_now_dt = datetime.now(ZoneInfo("Asia/Kolkata"))
                except Exception:
                    # Fallback: manual UTC +5:30 offset
                    ist_now_dt = datetime.utcnow() + timedelta(hours=5, minutes=30)
                ist_now = ist_now_dt.time()
                parts = str(allowed_after).strip().split(":")
                h = int(parts[0])
                m = int(parts[1])
                s = int(parts[2]) if len(parts) > 2 else 0
                gate = dtime(h, m, s)
                if (ist_now.hour, ist_now.minute, ist_now.second) < (
                    gate.hour,
                    gate.minute,
                    gate.second,
                ):
                    print(
                        f"Tests may only be run after {gate.strftime('%H:%M:%S')} IST. Current IST time: {ist_now.strftime('%H:%M:%S')}."
                    )
                    sys.exit(1)
            except Exception:
                print(
                    f"Warning: Could not parse allowed_after='{allowed_after}' for IST gating. Proceeding without gate."
                )

    print("Tests loaded successfully. Running validation...")
    env_vars = load_env_file()

    # Prefer SAMPLE_* or EVAL_* variables; fallback to legacy DB_* if unset
    def extract_db(prefix: str):
        return {
            "host": os.environ.get(
                f"{prefix}_DB_HOST", env_vars.get(f"{prefix}_DB_HOST", "127.0.0.1")
            ),
            "port": int(
                os.environ.get(
                    f"{prefix}_DB_PORT", env_vars.get(f"{prefix}_DB_PORT", 3306)
                )
            ),
            "user": os.environ.get(
                f"{prefix}_DB_USER", env_vars.get(f"{prefix}_DB_USER", "root")
            ),
            "password": os.environ.get(
                f"{prefix}_DB_PASS", env_vars.get(f"{prefix}_DB_PASS", "")
            ),
            "database": os.environ.get(
                f"{prefix}_DB_NAME", env_vars.get(f"{prefix}_DB_NAME", "")
            ),
        }

    db_config = extract_db("EVAL" if eval_mode else "SAMPLE")
    if not db_config.get("database"):
        legacy = get_db_config(env_vars)
        db_config.update({k: legacy.get(k, v) for k, v in db_config.items()})
    runner = TestRunner(tests_data, db_config)
    results = runner.run_tests(solution_path)
    print_results(results)

    if args.zip:
        save_encrypted_report_and_zip(results, solution_path, args.student_id)
    else:
        print(
            "(Skipping report save; run with --zip to generate encrypted results and ZIP.)"
        )

    if "error" in results:
        sys.exit(1)
    elif results["total_score"] < results["max_score"]:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
