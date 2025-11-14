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
from pathlib import Path
import json
from typing import Dict, List, Any, Tuple
import re
import argparse
import zipfile
import logging
from datetime import datetime, timedelta, time as dtime

# ENCRYPTION KEY - SET BY INSTRUCTOR BEFORE DISTRIBUTION
ENCRYPTION_KEY = b"nVPZZCjg6EFcWrch2Ivk13WWXNv7uWZGU5C5Vc2ADrw="  # Set automatically by build process

# Ensure repository root is importable when running as a script
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Import local modules
try:
    from shared.sql_parser import parse_sql
    from shared.db_utils import get_db_connection
    from student.config import get_db_config, load_env_file
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure required files are present.")
    sys.exit(1)

try:
    import pymysql  # type: ignore
except ImportError:
    print("Error: PyMySQL not installed. Please install it with:")
    print("    pip install pymysql")
    sys.exit(1)

try:
    from cryptography.fernet import Fernet  # type: ignore

    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    ZoneInfo = None  # type: ignore

# Externalized helpers (DRY) imported from test_utils
try:
    from test_utils import (
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
except ImportError:
    # If the helper module is missing, continue with in-file implementations.
    _util_load_and_decrypt_tests = None
    _util_save_encrypted_report_and_zip = None
    _util_print_results = None


def _load_and_decrypt_tests(encrypted_path: Path) -> Dict:
    """
    Load and decrypt eval_tests.json.enc file.
    (Moved from TestRunner staticmethod as it's a utility used before instantiation)
    """
    if not ENCRYPTION_KEY or ENCRYPTION_KEY == b"":
        raise Exception("Encryption key not set. Contact instructor.")

    if not CRYPTO_AVAILABLE:
        raise Exception("Cryptography library not available.")

    try:
        # Read encrypted file
        encrypted_data = encrypted_path.read_bytes()

        # Decrypt
        fernet = Fernet(ENCRYPTION_KEY)
        decrypted_data = fernet.decrypt(encrypted_data)

        # Parse JSON
        tests = json.loads(decrypted_data.decode("utf-8"))
        return tests

    except Exception as e:
        raise Exception(f"Failed to decrypt tests: {e}")


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

    def _make_result(
        self,
        test_key: str,
        test_data: Dict,
        status: str,
        message: str,
        score_mult: float,
        **extra_data: Any,
    ) -> Dict:
        """Consolidated result dictionary factory."""
        max_score = test_data.get("score", 1)
        score = max_score * score_mult
        return {
            "test": test_key,
            "status": status,
            "message": message,
            "score": score,
            "max_score": max_score,
            **extra_data,
        }

    def test_select_query(
        self, test_key: str, test_data: Dict, student_query: str, conn
    ) -> Dict:
        """Test a SELECT query by comparing outputs."""
        instructor_query = test_data.get("query", "")

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
        test_query = test_data.get("test_query")
        expected_output = test_data.get("expected_output", [])

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
        test_query = test_data.get("test_query")
        expected_output = test_data.get("expected_output", [])
        validation_query = test_data.get("validation_query")
        validation_output = test_data.get("validation_output", [])

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
        function_tests = test_data.get("function_tests", [])

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
            test_query = func_test.get("test_query")
            expected_output = func_test.get("expected_output", [])

            if not test_query:
                continue

            success, result = _execute_query(test_query, conn)
            if not success:
                failed_tests.append(f"Test {idx+1}: Query error - {result}")
                continue

            actual_output = _normalize_output(result)
            match, diff_msg = _compare_outputs(actual_output, expected_output)
            if not match:
                failed_tests.append(f"Test {idx+1}: {diff_msg}")

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
        test_query = test_data.get("test_query")
        expected_output = test_data.get("expected_output", [])

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
        student_queries = {
            f"q{i+1}": {"query": p.get("query", ""), "type": p.get("type", "unknown")}
            for i, p in enumerate(parsed_queries)
        }

        total_score = 0
        max_score = 0
        test_results = []

        # Connect to database using a context manager
        try:
            print("config: ", self.db_config)
            with get_db_connection(self.db_config) as conn:
                # Run tests for each query (sorted numerically)
                def sort_key(k):
                    match = re.search(r"\d+", k)
                    return int(match.group()) if match else 0

                for test_key in sorted(self.tests.keys(), key=sort_key):
                    test_data = self.tests[test_key]
                    max_score += test_data.get("score", 1)

                    if test_key not in student_queries:
                        result = _missing_result(
                            test_key,
                            test_data,
                            f"Student solution missing query {test_key}",
                        )
                        test_results.append(result)
                        continue

                    student_data = student_queries[test_key]
                    student_query = student_data["query"]
                    student_type = student_data.get("type", "unknown")
                    query_type = test_data.get("query_type", "").lower()

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

        except Exception as e:
            return {
                "error": f"Failed to connect to database or run tests: {e}",
                "total_score": 0,
                "max_score": max_score,
                "test_results": test_results,
            }

        return {
            "total_score": total_score,
            "max_score": max_score,
            "percentage": (total_score / max_score * 100) if max_score > 0 else 0,
            "test_results": test_results,
        }


def print_results(results: Dict):
    """Print test results in a readable format."""

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

        if status == "PASS":
            indicator, status_line = f"{GREEN}✓{RESET}", f"{GREEN}{status}{RESET}"
        elif status == "FAIL":
            indicator, status_line = f"{RED}✗{RESET}", f"{RED}{status}{RESET}"
        elif status in ("ERROR", "WARNING"):
            indicator, status_line = f"{YELLOW}⚠{RESET}", f"{YELLOW}{status}{RESET}"
        else:
            indicator, status_line = "?", status

        print(f"\n{indicator} {test_key}: {status_line} ({score}/{max_score} points)")
        print(f"   {message}")

        if "failures" in result:
            for failure in result["failures"]:
                print(f"     - {failure}")
        if (
            status in ("FAIL", "WARNING")
            and "expected" in result
            and "actual" in result
        ):
            print(f"   Expected: {result['expected']}")
            print(f"   Actual:   {result['actual']}")

    print("\n" + "=" * 70)
    total = results.get("total_score", 0)
    max_s = results.get("max_score", 0)
    perc = results.get("percentage", 0)
    color = GREEN if total == max_s and max_s > 0 else RED
    print(f"FINAL SCORE: {color}{total}{RESET}/{max_s} ({perc:.2f}%){RESET}")
    print("=" * 70 + "\n")


def save_encrypted_report_and_zip(results: Dict, solution_path: Path, student_id: str):
    """When --zip is used: create encrypted results.json.enc and submission zip."""

    # Prepare metadata
    results_with_metadata = {
        "student_id": student_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **results,
    }

    # Build minimal encrypted payload
    encrypted_report_name = f"{student_id}_results.json.enc"
    encrypted_report_path = Path.cwd() / encrypted_report_name

    try:
        if not (CRYPTO_AVAILABLE and ENCRYPTION_KEY):
            print("Skipping encryption: cryptography or key unavailable.")
            return

        questions = {
            tr.get("test", ""): (
                "Pass"
                if tr.get("status") == "PASS"
                else (tr.get("message") or tr.get("status") or "FAIL")
            )
            for tr in results.get("test_results", [])
        }

        minimal_payload = {
            "student_id": student_id,
            "timestamp": results_with_metadata["timestamp"],
            "total_score": results.get("total_score", 0),
            "questions": questions,
        }

        fernet = Fernet(ENCRYPTION_KEY)
        encrypted_data = fernet.encrypt(
            json.dumps(minimal_payload, indent=2).encode("utf-8")
        )
        encrypted_report_path.write_bytes(encrypted_data)
        print(f"Encrypted results saved: {encrypted_report_path.name}")

    except Exception as e:
        print(f"Failed to create encrypted results: {e}")
        return

    # Create ZIP containing solution.sql and encrypted results
    zip_path = Path.cwd() / f"{student_id}_submission.zip"
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if solution_path.exists():
                zf.write(solution_path, arcname="solution.sql")
            if encrypted_report_path.exists():
                zf.write(encrypted_report_path, arcname=encrypted_report_path.name)
        print(f"Submission ZIP created: {zip_path.name}")
        print(f"Files inside: solution.sql, {encrypted_report_path.name}")
    except Exception as e:
        print(f"Failed to create submission zip: {e}")


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
        action="store_true",
        help="Run in evaluation mode: use encrypted tests and create an encrypted submission zip.",
    )
    parser.add_argument(
        "--student-id",
        dest="student_id",
        help="Student ID required with --zip (format: YYYY[A-Z][A-Z0-9][A-Z][A-Z0-9][0-9]{4}g)",
    )
    args = parser.parse_args()

    # --- Mode and Path Setup (using pathlib) ---
    eval_mode = args.zip
    student_id = ""

    # Use Path.cwd() as the base for all relative paths
    cwd = Path.cwd()
    solution_path = Path(args.solution)
    if not solution_path.is_absolute():
        solution_path = cwd / solution_path

    # Validate student_id if in eval mode
    if eval_mode:
        sid = (args.student_id or "").strip()
        if not sid:
            print("Error: --student-id is required when using --zip")
            sys.exit(2)

        sid_norm = sid.lower()
        if not re.fullmatch(
            r"\d{4}[a-z][a-z0-9][a-z][a-z0-9]\d{4}g", sid_norm, flags=re.I
        ):
            print(
                "Error: Invalid student ID format. Expected YYYY[A-Z][A-Z0-9][A-Z][A-Z0-9][0-9]{4}g"
            )
            sys.exit(2)
        student_id = sid_norm  # Use the normalized ID

    # --- Load Test Data ---
    if not solution_path.exists():
        print(f"Error: Solution file not found: {solution_path}")
        sys.exit(1)

    try:
        if eval_mode:
            tests_path = cwd / "eval_tests.json.enc"
            if not tests_path.exists():
                print(f"Error: Encrypted evaluation tests file not found: {tests_path}")
                sys.exit(1)
            print("Loading encrypted evaluation tests...")
            if _util_load_and_decrypt_tests:
                tests_data = _util_load_and_decrypt_tests(
                    tests_path, ENCRYPTION_KEY, CRYPTO_AVAILABLE
                )
            else:
                tests_data = _load_and_decrypt_tests(tests_path)
        else:
            tests_path = cwd / "sample_tests.json.enc"
            if not tests_path.exists():
                print(f"Error: Sample tests file not found: {tests_path}")
                sys.exit(1)
            print("Loading sample tests...")
            if _util_load_and_decrypt_tests:
                tests_data = _util_load_and_decrypt_tests(
                    tests_path, ENCRYPTION_KEY, CRYPTO_AVAILABLE
                )
            else:
                tests_data = _load_and_decrypt_tests(tests_path)
    except Exception as e:
        print(f"Error loading tests: {e}")
        sys.exit(1)

    # --- Enforce Time Gate (Eval Mode Only) ---
    if eval_mode:
        first_test = (
            next(iter(tests_data.values()), {}) if isinstance(tests_data, dict) else {}
        )
        allowed_after = first_test.get("allowed_after")
        if allowed_after:
            try:
                # Use zoneinfo if available, else fallback to manual offset
                if ZoneInfo:
                    ist_now_dt = datetime.now(ZoneInfo("Asia/Kolkata"))
                else:
                    ist_now_dt = datetime.utcnow() + timedelta(hours=5, minutes=30)

                ist_now = ist_now_dt.time()
                parts = str(allowed_after).strip().split(":")
                gate = dtime(
                    int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0
                )

                if ist_now < gate:
                    print(
                        f"Tests may only be run after {gate.strftime('%H:%M:%S')} IST. Current IST time: {ist_now.strftime('%H:%M:%S')}."
                    )
                    sys.exit(1)
            except (ValueError, IndexError, TypeError) as e:
                # Catch specific parsing errors, not all exceptions
                print(
                    f"Warning: Could not parse allowed_after='{allowed_after}' for IST gating: {e}. Proceeding..."
                )
            except Exception as e:
                # Catch other potential errors (like invalid timezone)
                print(f"Warning: Error during time-gate check: {e}. Proceeding...")

    print("Tests loaded successfully. Running validation...")

    # --- DB Config ---
    env_vars = load_env_file()
    print(load_env_file)

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
    print("Extraction", db_config)
    if not db_config.get("database"):
        legacy = get_db_config(env_vars)
        db_config.update({k: legacy.get(k, v) for k, v in db_config.items()})

    # --- Run and Print ---
    runner = TestRunner(tests_data, db_config)
    results = runner.run_tests(solution_path)
    if _util_print_results:
        _util_print_results(results)
    else:
        print_results(results)

    if eval_mode:
        if _util_save_encrypted_report_and_zip:
            _util_save_encrypted_report_and_zip(
                results, solution_path, student_id, ENCRYPTION_KEY, CRYPTO_AVAILABLE
            )
        else:
            save_encrypted_report_and_zip(results, solution_path, student_id)
    else:
        print(
            "(Skipping report save; run with --zip to generate encrypted results and ZIP.)"
        )

    # --- Exit Status ---
    if "error" in results:
        sys.exit(1)
    elif results.get("total_score", 0) < results.get("max_score", 1):
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
