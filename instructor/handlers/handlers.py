#!/usr/bin/env python3
"""
handlers.py

HTTP request handlers for the test generation server.
"""
import json
import mimetypes
import os
import subprocess
import tempfile
import zipfile
import io
import sys
from urllib.parse import urlparse

from config import REPO_ROOT, WEB_DIR
from database.db_utils import (
    get_db_connection,
    reset_database_via_cli,
    is_pymysql_available,
)
from core.test_generator import check_constraints, generate_test_for_query

try:
    from core.sql_parser import parse_sql
except Exception:
    parse_sql = None

try:
    from cryptography.fernet import Fernet

    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


def build_student_executable():
    """
    Build the student executable with embedded encryption key.

    Returns:
        Tuple of (success: bool, message: str, executable_path: str or None)
    """
    try:
        # Get paths
        instructor_dir = os.path.dirname(os.path.abspath(__file__))  # handlers/ dir
        instructor_root = os.path.dirname(instructor_dir)  # instructor/ dir
        student_dir = os.path.join(instructor_root, "student")
        run_testcase_path = os.path.join(student_dir, "run_testcase.py")
        build_script = os.path.join(student_dir, "build_executable.sh")
        executable_path = os.path.join(student_dir, "dist", "run_testcase")

        # Check if student directory exists
        if not os.path.exists(student_dir):
            return False, f"Student directory not found: {student_dir}", None

        # Load encryption key
        key_path = os.path.join(REPO_ROOT, ".encryption_key")
        if not os.path.exists(key_path):
            return False, "Encryption key not found. Tests must be created first.", None

        with open(key_path, "rb") as f:
            key = f.read()

        # Update run_testcase.py with encryption key
        if not os.path.exists(run_testcase_path):
            return False, f"run_testcase.py not found: {run_testcase_path}", None

        with open(run_testcase_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Replace the empty key with actual key
        updated_content = content.replace(
            'ENCRYPTION_KEY = b""  # Instructor: Replace with actual key before creating executable',
            f"ENCRYPTION_KEY = {repr(key)}  # Set automatically by build process",
        )

        with open(run_testcase_path, "w", encoding="utf-8") as f:
            f.write(updated_content)

        # Check if build script exists
        if not os.path.exists(build_script):
            return False, f"Build script not found: {build_script}", None

        # Check if bash is available
        try:
            subprocess.run(
                ["bash", "--version"], capture_output=True, check=True, timeout=5
            )
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            return (
                False,
                "Bash is not available. On Windows, install WSL or Git Bash.",
                None,
            )

        # Make script executable
        try:
            os.chmod(build_script, 0o755)
        except Exception:
            pass  # May fail on Windows, that's ok

        # Run build script
        result = subprocess.run(
            ["bash", build_script],
            cwd=student_dir,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            return False, f"Build failed: {error_msg}", None

        # Check if executable was created
        if not os.path.exists(executable_path):
            return False, "Executable was not created", None

        # Get file size
        size_mb = os.path.getsize(executable_path) / (1024 * 1024)

        return (
            True,
            f"Executable built successfully ({size_mb:.2f} MB)",
            executable_path,
        )

    except subprocess.TimeoutExpired:
        return False, "Build timed out (exceeded 5 minutes)", None
    except Exception as e:
        return False, f"Build error: {str(e)}", None


def handle_parse(body, content_type):
    """
    Handle /parse endpoint - parse SQL script and return queries.

    Returns:
        Tuple of (status_code, response_body, content_type)
    """
    if parse_sql is None:
        return 500, "Server-side SQL parser not available", "text/plain"

    # Extract SQL text from request
    if "application/json" in content_type:
        try:
            payload = json.loads(body.decode("utf-8"))
            sql_text = payload.get("sql") if isinstance(payload, dict) else ""
        except Exception as e:
            return 400, f"Invalid JSON: {e}", "text/plain"
    else:
        try:
            sql_text = body.decode("utf-8")
        except Exception:
            sql_text = ""

    if not sql_text:
        return 400, "No SQL provided", "text/plain"

    try:
        items = parse_sql(sql_text)
        return 200, json.dumps(items, indent=2), "application/json"
    except Exception as e:
        return 500, f"Parser error: {e}", "text/plain"


def handle_reset_db(body, content_type, default_db_config):
    """
    Handle /reset-db endpoint - run SQL via mysql CLI.

    Returns:
        Tuple of (status_code, response_body, content_type)
    """
    # Extract SQL text and credentials
    if "application/json" in content_type:
        try:
            payload = json.loads(body.decode("utf-8"))
            sql_text = payload.get("sql") if isinstance(payload, dict) else ""
            # Get user-provided credentials or use defaults
            db_creds = (
                payload.get("db_credentials", {}) if isinstance(payload, dict) else {}
            )
        except Exception as e:
            return 400, f"Invalid JSON: {e}", "text/plain"
    else:
        try:
            sql_text = body.decode("utf-8")
            db_creds = {}
        except Exception:
            sql_text = ""
            db_creds = {}

    if not sql_text:
        return 400, "No SQL provided", "text/plain"

    # Merge user credentials with defaults
    db_config = {
        "host": db_creds.get("host") or default_db_config.get("host", "127.0.0.1"),
        "port": db_creds.get("port") or default_db_config.get("port", 3306),
        "user": db_creds.get("user") or default_db_config.get("user", "root"),
        "password": db_creds.get("password") or default_db_config.get("password", ""),
        "database": db_creds.get("database") or default_db_config.get("database", ""),
    }

    success, output = reset_database_via_cli(sql_text, db_config, REPO_ROOT)
    return (200 if success else 500), output, "text/plain"


def handle_test_connection(body, default_db_config):
    """
    Handle /test-connection endpoint - test database connection.

    Returns:
        Tuple of (status_code, response_body, content_type)
    """
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as e:
        return 400, f"Invalid JSON: {e}", "text/plain"

    # Merge user credentials with defaults
    db_config = {
        "host": payload.get("host") or default_db_config.get("host", "127.0.0.1"),
        "port": payload.get("port") or default_db_config.get("port", 3306),
        "user": payload.get("user") or default_db_config.get("user", "root"),
        "password": payload.get("password") or default_db_config.get("password", ""),
        "database": payload.get("database") or default_db_config.get("database", ""),
    }

    # Try to connect
    try:
        conn = get_db_connection(db_config)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return 200, "Connection successful", "text/plain"
    except Exception as e:
        return 500, f"Connection failed: {str(e)}", "text/plain"


def _generate_tests(items_obj, db_config, allowed_after):
    """Internal helper to generate tests dict given items and db config."""
    if not is_pymysql_available():
        raise RuntimeError(
            "PyMySQL not installed. Please install PyMySQL to create tests."
        )

    # Connect
    conn = get_db_connection(db_config)
    output_tests = {}

    # Sort keys numerically
    def sort_key(k):
        import re

        match = re.search(r"\d+", k)
        return int(match.group()) if match else 0

    keys = sorted(items_obj.keys(), key=sort_key)
    try:
        cursor = conn.cursor()
        for key in keys:
            item = items_obj[key]
            query = item.get("query", "")
            qtype = (item.get("type") or item.get("query_type") or "").lower()
            score = item.get("score", 1)
            test_json = {"query": query, "query_type": qtype, "score": score}
            for flag in (
                "require_join",
                "forbid_join",
                "require_nested_select",
                "forbid_nested_select",
                "require_group_by",
                "forbid_group_by",
                "require_order_by",
                "forbid_order_by",
            ):
                if flag in item:
                    test_json[flag] = item[flag]
            violations = check_constraints(query, item)
            if violations:
                test_json["constraint_violations"] = violations
                output_tests[key] = test_json
                continue
            test_result = generate_test_for_query(query, qtype.strip(), item, cursor)
            test_json.update(test_result)
            if allowed_after:
                test_json["allowed_after"] = allowed_after
            output_tests[key] = test_json
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
    return output_tests


def handle_create_tests(body, default_db_config):
    """
    Handle /create-tests endpoint - generate dual test artifacts:
      - sample_tests.json (unencrypted practice tests)
      - tests.json / tests.json.enc (evaluation tests) for packaging

    Accepts payload with sample_db_credentials and eval_db_credentials.
    """
    # Parse payload
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as e:
        return 400, f"Invalid JSON: {e}", "text/plain"

    # Extract separate credentials
    sample_creds = (
        payload.get("sample_db_credentials", {}) if isinstance(payload, dict) else {}
    )
    eval_creds = (
        payload.get("eval_db_credentials", {}) if isinstance(payload, dict) else {}
    )

    def merged(creds):
        return {
            "host": creds.get("host") or default_db_config.get("host", "127.0.0.1"),
            "port": creds.get("port") or default_db_config.get("port", 3306),
            "user": creds.get("user") or default_db_config.get("user", "root"),
            "password": creds.get("password", default_db_config.get("password", "")),
            "database": creds.get("database") or default_db_config.get("database", ""),
        }

    sample_db_config = merged(sample_creds)
    eval_db_config = merged(eval_creds)

    # Normalize payload to dict keyed by q1..qN
    if isinstance(payload, dict) and "queries" in payload:
        # New format: {queries: [...], db_credentials: {...}}
        queries_list = payload.get("queries", [])
        items_obj = {f"q{i+1}": queries_list[i] for i in range(len(queries_list))}
        allowed_after = payload.get("allowed_after")
    elif isinstance(payload, list):
        # Legacy format: array of queries
        items_obj = {f"q{i+1}": payload[i] for i in range(len(payload))}
        allowed_after = None
    elif isinstance(payload, dict):
        # Legacy format: object with query keys (filter out db_credentials)
        items_obj = {k: v for k, v in payload.items() if k != "db_credentials"}
        allowed_after = payload.get("allowed_after")
    else:
        return 400, "Payload must be an array or object of tests", "text/plain"

    # Generate sample tests
    try:
        sample_tests = _generate_tests(items_obj, sample_db_config, allowed_after)
    except Exception as e:
        return 500, f"Failed to generate sample tests: {e}", "text/plain"

    # Generate evaluation tests
    try:
        eval_tests = _generate_tests(items_obj, eval_db_config, allowed_after)
    except Exception as e:
        return 500, f"Failed to generate evaluation tests: {e}", "text/plain"

    # Persist artifacts
    try:
        # sample_tests.json (plain)
        with open(
            os.path.join(REPO_ROOT, "sample_tests.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(sample_tests, f, indent=4)
        # tests.json (evaluation, plain copy before encryption for instructor)
        with open(os.path.join(REPO_ROOT, "tests.json"), "w", encoding="utf-8") as f:
            json.dump(eval_tests, f, indent=4)
        # tests_debug.json for instructor troubleshooting (evaluation)
        with open(
            os.path.join(REPO_ROOT, "tests_debug.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(eval_tests, f, indent=4)
    except Exception as e:
        return 500, f"Failed to write test artifacts: {e}", "text/plain"

    # Build student executable automatically
    build_success, build_message, executable_path = build_student_executable()

    response_data = {
        "sample_tests": sample_tests,
        "eval_tests": eval_tests,
        "build_status": {
            "success": build_success,
            "message": build_message,
            "executable_ready": executable_path is not None,
        },
    }

    if build_success:
        pass
    else:
        pass

    return 200, json.dumps(response_data, indent=2), "application/json"


def handle_static_file(path):
    """
    Handle static file serving.

    Returns:
        Tuple of (status_code, response_body, content_type)
    """
    if path == "/":
        rel = "index.html"
    else:
        rel = path.lstrip("/")

    requested = os.path.normpath(os.path.join(WEB_DIR, rel))

    # Security check: prevent path traversal
    if not requested.startswith(WEB_DIR):
        return 403, "Forbidden", "text/plain"

    if os.path.isdir(requested):
        requested = os.path.join(requested, "index.html")

    if not os.path.exists(requested):
        return 404, "Not found", "text/plain"

    try:
        with open(requested, "rb") as f:
            data = f.read()
        ctype, _ = mimetypes.guess_type(requested)
        if not ctype:
            ctype = "application/octet-stream"
        return 200, data, ctype
    except Exception as e:
        return 500, f"Failed to read file: {e}", "text/plain"


def handle_create_package(body, content_type):
    """
    Handle /create-package endpoint - create encrypted zip package for students.

    Creates a ZIP containing:
    - questions.pdf (if provided)
    - solution.sql (empty template annotated with constraints)
    - eval_tests.json.enc (encrypted evaluation tests)
    - sample_tests.json (plain practice tests)
    - .env.local (sample & evaluation database credentials)
    - run_testcase (executable)

    Returns:
        Tuple of (status_code, response_body, content_type)
    """
    if not CRYPTO_AVAILABLE:
        return (
            500,
            "Cryptography library not installed. Run: pip install cryptography",
            "text/plain",
        )

    # Parse multipart form data to extract credentials and PDF
    db_credentials = None
    pdf_content = None

    if "multipart/form-data" in content_type:
        try:
            boundary = content_type.split("boundary=")[1].encode()
            parts = body.split(b"--" + boundary)

            for part in parts:
                if b'name="db_credentials"' in part:
                    # Extract credentials JSON
                    header_end = part.find(b"\r\n\r\n")
                    if header_end != -1:
                        creds_data = part[header_end + 4 :].rstrip(b"\r\n")
                        if creds_data:
                            db_credentials = json.loads(creds_data.decode("utf-8"))

                elif b'name="questions_pdf"' in part:
                    # Extract PDF content
                    header_end = part.find(b"\r\n\r\n")
                    if header_end != -1:
                        pdf_content = part[header_end + 4 :].rstrip(b"\r\n")
        except Exception as e:
            print(f"[WARNING] Failed to parse form data: {e}")

    # Require both sample_tests.json and tests.json (evaluation) to exist
    tests_json_path = os.path.join(REPO_ROOT, "tests.json")  # evaluation tests plain
    sample_tests_path = os.path.join(REPO_ROOT, "sample_tests.json")
    if not os.path.exists(tests_json_path) or not os.path.exists(sample_tests_path):
        return (
            400,
            "Required test artifacts missing. Create tests first (both sample and eval).",
            "text/plain",
        )

    try:
        # Read evaluation tests (to encrypt) and sample tests (plain)
        with open(tests_json_path, "r", encoding="utf-8") as f:
            eval_tests_content = f.read()
        with open(sample_tests_path, "r", encoding="utf-8") as f:
            sample_tests_content = f.read()

        # Generate encryption key (or load from config)
        # For production, store this key securely and provide it to the grading system
        key_path = os.path.join(REPO_ROOT, ".encryption_key")
        if os.path.exists(key_path):
            with open(key_path, "rb") as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(key_path, "wb") as f:
                f.write(key)

        # Encrypt evaluation tests
        fernet = Fernet(key)
        encrypted_eval_tests = fernet.encrypt(eval_tests_content.encode("utf-8"))

        # Parse evaluation tests to create a helpful solution.sql template
        tests_data = json.loads(eval_tests_content)
        solution_template = "-- Student Solution\n"
        solution_template += "-- Write your SQL queries below\n"
        solution_template += "-- Each query should be separated by semicolons\n"
        solution_template += "-- If you don't know the answer to a question, just write a semicolon (;)\n\n"

        # Sort test keys numerically
        def sort_key(k):
            import re

            match = re.search(r"\d+", k)
            return int(match.group()) if match else 0

        for test_key in sorted(tests_data.keys(), key=sort_key):
            test = tests_data[test_key]
            query_type = test.get("query_type", "unknown")

            # Build constraint hints
            constraints = []
            if test.get("require_join"):
                constraints.append("must use JOIN")
            if test.get("forbid_join"):
                constraints.append("without JOIN")
            if test.get("require_nested_select"):
                constraints.append("must use subquery")
            if test.get("forbid_nested_select"):
                constraints.append("without subquery")
            if test.get("require_group_by"):
                constraints.append("must use GROUP BY")
            if test.get("forbid_group_by"):
                constraints.append("without GROUP BY")
            if test.get("require_order_by"):
                constraints.append("must use ORDER BY")
            if test.get("forbid_order_by"):
                constraints.append("without ORDER BY")

            # Create comment line
            constraint_text = f" ({', '.join(constraints)})" if constraints else ""
            solution_template += (
                f"-- {test_key.upper()}: {query_type.upper()}{constraint_text}\n"
            )
            solution_template += "\n\n\n"

        solution_template += "-- End of solution\n"

        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # Add encrypted evaluation tests & plain sample tests
            zip_file.writestr("eval_tests.json.enc", encrypted_eval_tests)
            zip_file.writestr("sample_tests.json", sample_tests_content)

            # Add solution.sql template (generated above with constraints)
            zip_file.writestr("solution.sql", solution_template)

            # Add run_testcase executable if it exists
            instructor_dir = os.path.dirname(os.path.abspath(__file__))  # handlers/ dir
            instructor_root = os.path.dirname(instructor_dir)  # instructor/ dir
            student_dir = os.path.join(instructor_root, "student")
            executable_path = os.path.join(student_dir, "dist", "run_testcase")

            if os.path.exists(executable_path):
                with open(executable_path, "rb") as exe_file:
                    zip_file.writestr("run_testcase", exe_file.read())

            # Add .env.local with database credentials
            if db_credentials:
                # Accept combined credentials object {sample_db_credentials:{}, eval_db_credentials:{}}
                sample_creds = db_credentials.get("sample_db_credentials", {})
                eval_creds = db_credentials.get("eval_db_credentials", {})
                env_local_content = f"""# Database Configuration (Sample & Evaluation)
# Auto-generated by instructor's test creation tool
# These credentials are pre-configured for testing

# Sample (practice) database
SAMPLE_DB_HOST={sample_creds.get('host', 'localhost')}
SAMPLE_DB_PORT={sample_creds.get('port', 3306)}
SAMPLE_DB_USER={sample_creds.get('user', 'root')}
SAMPLE_DB_PASS={sample_creds.get('password', '')}
SAMPLE_DB_NAME={sample_creds.get('database', '')}

# Evaluation database
EVAL_DB_HOST={eval_creds.get('host', 'localhost')}
EVAL_DB_PORT={eval_creds.get('port', 3306)}
EVAL_DB_USER={eval_creds.get('user', 'root')}
EVAL_DB_PASS={eval_creds.get('password', '')}
EVAL_DB_NAME={eval_creds.get('database', '')}
"""
                zip_file.writestr(".env.local", env_local_content)

            # Add questions.pdf if provided
            if pdf_content:
                zip_file.writestr("questions.pdf", pdf_content)

        zip_buffer.seek(0)
        return 200, zip_buffer.getvalue(), "application/zip"

    except Exception as e:
        return 500, f"Failed to create package: {e}", "text/plain"
