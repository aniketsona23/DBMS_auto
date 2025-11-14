#!/usr/bin/env python3
"""
services.py

Service-layer functions used by HTTP handlers.
"""
import io
import json
import logging
from pathlib import Path
import re
import subprocess
from textwrap import dedent
import zipfile
from typing import Dict, Any, Optional, Tuple

from instructor.config import REPO_ROOT
from shared.db_utils import get_db_connection, is_pymysql_available
from instructor.utils.test_generator import check_constraints, generate_test_for_query
from instructor.utils.utils import sort_key_numeric, get_db_config_from_payload

try:
    from cryptography.fernet import Fernet  # type: ignore
except ImportError:
    Fernet = None
logger = logging.getLogger(__name__)

REPO_PATH = Path(REPO_ROOT)
STUDENT_DIR = REPO_PATH / "student"
KEY_PATH = REPO_PATH / ".encryption_key"

CONSTRAINT_FLAGS = [
    "require_join",
    "forbid_join",
    "require_nested_select",
    "forbid_nested_select",
    "require_group_by",
    "forbid_group_by",
    "require_order_by",
    "forbid_order_by",
]


def generate_tests(
    items_obj: Dict[str, Any], db_config: Dict[str, Any], allowed_after: Optional[str]
):
    """Generate tests dict given parsed items and DB config."""
    if not is_pymysql_available():
        raise RuntimeError(
            "PyMySQL not installed. Please install PyMySQL to create tests."
        )

    output_tests: Dict[str, Any] = {}
    keys = sorted(items_obj.keys(), key=sort_key_numeric)

    # Use context managers for safe resource handling
    with get_db_connection(db_config) as conn:
        with conn.cursor() as cursor:
            for key in keys:
                item = items_obj[key]
                query = item.get("query", "")
                qtype = (item.get("type") or item.get("query_type") or "").lower()
                score = item.get("score", 1)

                test_json = {"query": query, "query_type": qtype, "score": score}

                # Use the CONSTRAINT_FLAGS constant
                for flag in CONSTRAINT_FLAGS:
                    if flag in item:
                        test_json[flag] = item[flag]

                violations = check_constraints(query, item)
                if violations:
                    test_json["constraint_violations"] = violations
                    output_tests[key] = test_json
                    continue

                test_result = generate_test_for_query(
                    query, qtype.strip(), item, cursor
                )
                test_json.update(test_result)
                if allowed_after:
                    test_json["allowed_after"] = allowed_after
                output_tests[key] = test_json

    return output_tests


def build_student_executable() -> Tuple[bool, str, Optional[str]]:
    """
    Build the student executable with embedded encryption key.

    Returns tuple: (success: bool, message: str, executable_path: str | None)
    """
    run_testcase_path = STUDENT_DIR / "run_testcase.py"
    build_script = REPO_PATH / "instructor" / "scripts" / "build_executable.sh"
    executable_path = STUDENT_DIR / "dist" / "run_testcase"
    original_content = ""

    try:
        if not STUDENT_DIR.exists():
            return False, f"Student directory not found: {STUDENT_DIR}", None
        if not KEY_PATH.exists():
            return False, "Encryption key not found. Tests must be created first.", None
        if not run_testcase_path.exists():
            return False, f"run_testcase.py not found: {run_testcase_path}", None
        if not build_script.exists():
            return False, f"Build script not found: {build_script}", None

        # --- Check for Bash ---
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

        # --- Modify run_testcase.py (Safely) ---
        with open(KEY_PATH, "rb") as f:
            key = f.read()

        original_content = run_testcase_path.read_text(encoding="utf-8")

        pattern = r"^ENCRYPTION_KEY\s*=.*$"
        replacement = (
            f"ENCRYPTION_KEY = {repr(key)}  # Set automatically by build process"
        )

        updated_content, n = re.subn(pattern, replacement, original_content, flags=re.M)
        if n == 0:
            updated_content = replacement + "\n" + original_content

        run_testcase_path.write_text(updated_content, encoding="utf-8")

        # --- Run Build Script ---
        build_script.chmod(0o755)

        result = subprocess.run(
            ["bash", str(build_script)],
            cwd=str(STUDENT_DIR),
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            return False, f"Build failed: {error_msg}", None

        if not executable_path.exists():
            return False, "Executable was not created", None

        size_mb = executable_path.stat().st_size / (1024 * 1024)
        return (
            True,
            f"Executable built successfully ({size_mb:.2f} MB)",
            str(executable_path),
        )

    except subprocess.TimeoutExpired:
        return False, "Build timed out (exceeded 5 minutes)", None
    except Exception as e:
        logger.exception("Build executable failed")
        return False, f"Build error: {str(e)}", None
    finally:
        # **CRITICAL:** Restore the original file content
        if original_content and run_testcase_path.exists():
            try:
                run_testcase_path.write_text(original_content, encoding="utf-8")
                logger.info("Restored original run_testcase.py")
            except Exception as e:
                logger.error(f"Failed to restore run_testcase.py: {e}")


def build_list_scores_executable() -> Tuple[bool, str, Optional[str]]:
    """
    Build the list_scores executable from decrypt_and_append.py with embedded encryption key.
    If the executable already exists, skip the build process.

    Returns tuple: (success: bool, message: str, executable_path: str | None)
    """
    decrypt_script_path = REPO_PATH / "instructor" / "utils" / "decrypt_and_append.py"
    output_dir = REPO_PATH / "instructor" / "dist"
    executable_path = output_dir / "list_scores"
    original_content = ""

    try:
        # Check if executable already exists
        if executable_path.exists():
            size_mb = executable_path.stat().st_size / (1024 * 1024)
            logger.info(f"list_scores executable already exists, skipping build")
            return (
                True,
                f"list_scores executable already exists ({size_mb:.2f} MB) - skipped build",
                str(executable_path),
            )

        if not decrypt_script_path.exists():
            return (
                False,
                f"decrypt_and_append.py not found: {decrypt_script_path}",
                None,
            )
        if not KEY_PATH.exists():
            return False, "Encryption key not found. Tests must be created first.", None

        # Check for Bash
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

        # Embed encryption key in decrypt_and_append.py
        with open(KEY_PATH, "rb") as f:
            key = f.read()

        original_content = decrypt_script_path.read_text(encoding="utf-8")

        # Replace the default key with actual key
        pattern = r'key = b"[^"]+"'
        replacement = f"key = {repr(key)}"

        updated_content = re.sub(pattern, replacement, original_content)
        decrypt_script_path.write_text(updated_content, encoding="utf-8")

        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # Build with PyInstaller
        result = subprocess.run(
            [
                "pyinstaller",
                "--onefile",
                "--name",
                "list_scores",
                "--clean",
                "--noconfirm",
                "--distpath",
                str(output_dir),
                str(decrypt_script_path),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            return False, f"Build failed: {error_msg}", None

        if not executable_path.exists():
            return False, "Executable was not created", None

        size_mb = executable_path.stat().st_size / (1024 * 1024)
        return (
            True,
            f"list_scores executable built successfully ({size_mb:.2f} MB)",
            str(executable_path),
        )

    except subprocess.TimeoutExpired:
        return False, "Build timed out (exceeded 5 minutes)", None
    except Exception as e:
        logger.exception("Build list_scores executable failed")
        return False, f"Build error: {str(e)}", None
    finally:
        # Restore original file content
        if original_content and decrypt_script_path.exists():
            try:
                decrypt_script_path.write_text(original_content, encoding="utf-8")
                logger.info("Restored original decrypt_and_append.py")
            except Exception as e:
                logger.error(f"Failed to restore decrypt_and_append.py: {e}")


def _get_or_create_key() -> bytes:
    """Loads or generates a new encryption key."""
    if Fernet is None:
        raise ImportError(
            "Cryptography library not installed. Run: pip install cryptography"
        )

    if KEY_PATH.exists():
        return KEY_PATH.read_bytes()

    key = Fernet.generate_key()
    KEY_PATH.write_bytes(key)
    return key


def create_student_package(
    eval_tests_content: str,
    sample_tests_content: str,
    db_credentials: Optional[Dict[str, Any]] = None,
    pdf_content: Optional[bytes] = None,
) -> Tuple[bool, Optional[bytes], Optional[str]]:
    """Create the student ZIP package."""
    try:
        key = _get_or_create_key()
        fernet = Fernet(key)
        encrypted_eval_tests = fernet.encrypt(eval_tests_content.encode("utf-8"))
        encrypted_sample_tests = fernet.encrypt(sample_tests_content.encode("utf-8"))

        # Build solution.sql template
        tests_data = json.loads(eval_tests_content)
        solution_template = dedent(
            """\
            -- Student Solution
            -- Write your SQL queries below
            -- Each query should be separated by semicolons
            -- If you don't know the answer to a question, just write a semicolon (;)

            """
        )

        for test_key in sorted(tests_data.keys(), key=sort_key_numeric):
            test = tests_data[test_key]
            query_type = test.get("query_type", "unknown")

            # Use the CONSTRAINT_FLAGS constant
            constraints = [
                flag.replace("_", " ")
                .replace("require ", "must use ")
                .replace("forbid ", "without ")
                for flag in CONSTRAINT_FLAGS
                if test.get(flag)
            ]

            constraint_text = f" ({', '.join(constraints)})" if constraints else ""
            solution_template += (
                f"-- {test_key.upper()}: {query_type.upper()}{constraint_text}\n;\n\n"
            )

        solution_template += "-- End of solution\n"

        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr("eval_tests.json.enc", encrypted_eval_tests)
            zip_file.writestr("sample_tests.json.enc", encrypted_sample_tests)
            zip_file.writestr("solution.sql", solution_template)

            # Add run_testcase if present
            executable_path = STUDENT_DIR / "dist" / "run_testcase"
            if executable_path.exists():
                zip_file.writestr("run_testcase", executable_path.read_bytes())

            # .env.local from combined credentials
            if db_credentials:
                sample_creds = db_credentials.get("sample_db_credentials", {})
                eval_creds = db_credentials.get("eval_db_credentials", {})
                env_local_content = dedent(
                    f"""\
                    # Database Configuration (Sample & Evaluation)
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
                )
                zip_file.writestr(".env.local", env_local_content)

            if pdf_content:
                zip_file.writestr("questions.pdf", pdf_content)

        zip_buffer.seek(0)
        return True, zip_buffer.getvalue(), None

    except Exception as e:
        logger.exception("Failed to create package")
        return False, None, f"Failed to create package: {e}"


def create_tests_artifacts(
    payload: Dict[str, Any],
) -> Tuple[bool, Optional[Dict], Optional[str], int]:
    """
    Create all test artifacts and build the student executable.

    Returns: (ok: bool, data: dict | None, err: str | None, status_code: int)
    """
    if not isinstance(payload, dict):
        return False, None, "VALIDATION: payload must be a JSON object", 400

    # Validate DB credentials
    sample_db_config, err_sample = get_db_config_from_payload(
        payload, "sample_db_credentials"
    )
    if err_sample:
        return False, None, f"VALIDATION: {err_sample}", 400

    eval_db_config, err_eval = get_db_config_from_payload(
        payload, "eval_db_credentials"
    )
    if err_eval:
        return False, None, f"VALIDATION: {err_eval}", 400

    # Normalize queries
    items_obj = {}
    allowed_after = None
    if "queries" in payload and isinstance(payload.get("queries"), list):
        queries_list = payload.get("queries", [])
        items_obj = {f"q{i+1}": queries_list[i] for i in range(len(queries_list))}
        allowed_after = payload.get("allowed_after")
    else:
        # Handle legacy formats
        items_obj = {
            k: v
            for k, v in payload.items()
            if k
            not in ("sample_db_credentials", "eval_db_credentials", "allowed_after")
        }
        allowed_after = payload.get("allowed_after")

    if not items_obj:
        return False, None, "VALIDATION: No queries provided", 400

    # --- Generate tests ---
    try:
        sample_tests = generate_tests(items_obj, sample_db_config, allowed_after)
        eval_tests = generate_tests(items_obj, eval_db_config, allowed_after)
    except Exception as e:
        logger.exception("Failed to generate tests")
        return False, None, f"Failed to generate tests: {e}", 500

    # --- Persist artifacts ---
    try:
        (REPO_PATH / "sample_tests.json").write_text(
            json.dumps(sample_tests, indent=4), encoding="utf-8"
        )
        (REPO_PATH / "tests.json").write_text(
            json.dumps(eval_tests, indent=4), encoding="utf-8"
        )
    except Exception as e:
        return False, None, f"Failed to write test artifacts: {e}", 500

    # --- Generate Key (if needed) & Build Executables ---
    try:
        _get_or_create_key()
    except Exception as e:
        return False, None, f"Failed to create/load encryption key: {e}", 500

    build_success, build_message, executable_path = build_student_executable()
    list_scores_success, list_scores_message, list_scores_path = (
        build_list_scores_executable()
    )

    response_data = {
        "sample_tests": sample_tests,
        "eval_tests": eval_tests,
        "build_status": {
            "success": build_success,
            "message": build_message,
            "executable_ready": executable_path is not None,
        },
        "list_scores_status": {
            "success": list_scores_success,
            "message": list_scores_message,
            "executable_ready": list_scores_path is not None,
            "executable_path": list_scores_path,
        },
    }

    return True, response_data, None, 200
