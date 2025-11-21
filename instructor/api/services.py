#!/usr/bin/env python3
"""
services.py

Service-layer functions used by HTTP handlers.
"""

import io
import json
import logging
from pathlib import Path
import subprocess
import zipfile
from typing import Dict, Any, List, Optional, Tuple, TypedDict
from shared.constants import (
    COMMON_BUILD_DIR,
    COMMON_DIST_DIR,
    PACKAGE_EVAL_TESTS_FILENAME,
    PACKAGE_SAMPLE_TESTS_FILENAME,
    REPO_PATH,
    STUDENT_DIR,
    KEY_PATH,
    RUN_TESTCASE_PATH,
    RUN_TESTCASE_EXECUTABLE_PATH,
    DECRYPT_SCRIPT_PATH,
    TESTS_JSON_PATH,
    SAMPLE_TESTS_JSON_PATH,
)
from shared.db_utils import get_db_connection, is_pymysql_available
from shared.constants import FieldNames, CONSTRAINT_FLAGS
from shared.encryption import get_or_create_key, encrypt_string
from shared.models import DBConfig
from typing import cast
from instructor.utils.test_generator import check_constraints, generate_test_for_query
from instructor.utils.utils import sort_key_numeric, get_db_config_from_payload

logger = logging.getLogger(__name__)


class BuildStatus(TypedDict):
    success: bool
    message: str
    executable_ready: bool


class TestsArtifactsResult(TypedDict):
    ok: bool
    data: Optional[Dict[str, Any]]
    err: Optional[str]
    status_code: int


def _get_size_mb(path: Path) -> float:
    """Returns file size in megabytes."""
    return path.stat().st_size / (1024 * 1024)


def _build_pyinstaller_executable(
    script_path: Path,
    name: str,
    spec_path: Path,
    hidden_imports: List[str],
    extra_args: Optional[List[str]] = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Generic helper to build a PyInstaller executable.

    Args:
        script_path: Path to the python script to freeze.
        name: Name of the output executable.
        spec_path: Path to store/look for the .spec file.
        hidden_imports: List of module names to include via --hidden-import.
        extra_args: List of additional PyInstaller arguments (e.g. UPX config).
    """
    executable_path = COMMON_DIST_DIR / name

    # 1. Check existing artifact
    if executable_path.exists():
        size_mb = _get_size_mb(executable_path)
        logger.info(f"{name} executable already exists, skipping build")
        return (
            True,
            f"{name} executable already exists ({size_mb:.2f} MB) - skipped build",
            str(executable_path),
        )

    # 2. Directory and Key Setup
    try:
        COMMON_DIST_DIR.mkdir(parents=True, exist_ok=True)
        COMMON_BUILD_DIR.mkdir(parents=True, exist_ok=True)
        get_or_create_key(KEY_PATH)
    except Exception as e:
        return False, f"Setup failed: {e}", None

    # 3. Construct Command
    cmd = [
        "pyinstaller",
        "--onefile",
        "--name",
        name,
        "--clean",
        "--noconfirm",
        "--distpath",
        str(COMMON_DIST_DIR),
        "--workpath",
        str(COMMON_BUILD_DIR / name),
        "--specpath",
        str(spec_path),
        f"--add-data={KEY_PATH}:shared",
        "--paths",
        str(REPO_PATH),
    ]

    for mod in hidden_imports:
        cmd.extend(["--hidden-import", mod])

    if extra_args:
        cmd.extend(extra_args)

    cmd.append(str(script_path))

    # 4. Execute Build
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(REPO_PATH),
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            return False, f"Build failed: {error_msg}", None

        if not executable_path.exists():
            return False, "Executable was not created (unknown error)", None

        size_mb = _get_size_mb(executable_path)
        return (
            True,
            f"{name} executable built successfully ({size_mb:.2f} MB)",
            str(executable_path),
        )

    except subprocess.TimeoutExpired:
        return False, "Build timed out (exceeded 5 minutes)", None
    except Exception as e:
        logger.exception(f"Build {name} executable failed")
        return False, f"Build error: {str(e)}", None


def generate_tests(items_obj: Dict[str, Any], db_config: DBConfig):
    """Generate tests dict given parsed items and DB config."""
    if not is_pymysql_available():
        raise RuntimeError(
            "PyMySQL not installed. Please install PyMySQL to create tests."
        )

    output_tests: Dict[str, Any] = {
        FieldNames.DB_CONFIG: db_config  # Embed database credentials
    }
    keys = sorted(items_obj.keys(), key=sort_key_numeric)

    with get_db_connection(db_config) as conn:
        with conn.cursor() as cursor:
            for key in keys:
                item = items_obj[key]
                query = item.get(FieldNames.QUERY, "")
                qtype = (
                    item.get("type") or item.get(FieldNames.QUERY_TYPE) or ""
                ).lower()
                score = item.get(FieldNames.SCORE, 1)

                mandatory_fields = {
                    FieldNames.QUERY: query,
                    FieldNames.QUERY_TYPE: qtype,
                    FieldNames.SCORE: score,
                }
                constraint_fields = {
                    flag: item[flag] for flag in CONSTRAINT_FLAGS if flag in item
                }
                test_json = {**mandatory_fields, **constraint_fields}

                violations = check_constraints(query, item)
                if violations:
                    test_json[FieldNames.CONSTRAINT_VIOLATIONS] = violations
                    output_tests[key] = test_json
                    continue

                test_result = generate_test_for_query(
                    query, qtype.strip(), item, cursor
                )
                test_json.update(test_result)
                output_tests[key] = test_json

    return output_tests


def build_student_executable() -> BuildStatus:
    """Build the student executable (run_testcase)."""
    if not STUDENT_DIR.exists():
        return False, f"Student directory not found: {STUDENT_DIR}", None
    if not RUN_TESTCASE_PATH.exists():
        return False, f"run_testcase.py not found: {RUN_TESTCASE_PATH}", None

    hidden_imports = [
        "shared",
        "shared.models",
        "shared.constants",
        "shared.sql_parser",
        "shared.db_utils",
        "student.test_utils",
        "pymysql",
        "cryptography",
    ]

    return _build_pyinstaller_executable(
        script_path=RUN_TESTCASE_PATH,
        name="run_testcase",
        spec_path=STUDENT_DIR,
        hidden_imports=hidden_imports,
    )


def build_list_scores_executable() -> BuildStatus:
    """Build the list_scores executable (decrypt_and_append)."""
    if not DECRYPT_SCRIPT_PATH.exists():
        return False, f"decrypt_and_append.py not found: {DECRYPT_SCRIPT_PATH}", None

    hidden_imports = [
        "cryptography",
        "shared",
        "shared.models",
        "shared.constants",
        "shared.sql_parser",
        "shared.db_utils",
        "shared.encryption",
    ]

    return _build_pyinstaller_executable(
        script_path=DECRYPT_SCRIPT_PATH,
        name="list_scores",
        spec_path=REPO_PATH,
        hidden_imports=hidden_imports,
    )


def create_student_package(
    eval_tests_content: str,
    sample_tests_content: str,
    db_credentials: Optional[Dict[str, Any]] = None,
    pdf_content: Optional[bytes] = None,
) -> Tuple[bool, Optional[bytes], Optional[str]]:
    """Create the student ZIP package."""
    try:
        key = get_or_create_key(KEY_PATH)
        encrypted_eval_tests = encrypt_string(eval_tests_content, key)
        encrypted_sample_tests = encrypt_string(sample_tests_content, key)

        # Build solution.sql template
        tests_data = json.loads(eval_tests_content)
        lines = [
            "-- Student Solution",
            "-- Write your SQL queries below",
            "-- Each query should be separated by semicolons",
            "-- If you don't know the answer to a question, just write a semicolon (;)",
            "",
        ]

        for test_key in sorted(tests_data.keys(), key=sort_key_numeric):
            test = tests_data[test_key]
            query_type = test.get(FieldNames.QUERY_TYPE, "unknown")

            # Use the CONSTRAINT_FLAGS constant
            constraints = [
                flag.replace("_", " ")
                .replace("require ", "must use ")
                .replace("forbid ", "without ")
                for flag in CONSTRAINT_FLAGS
                if test.get(flag)
            ]

            constraint_text = f" ({', '.join(constraints)})" if constraints else ""
            lines.append(
                f"-- {test_key.upper()}: {query_type.upper()}{constraint_text}"
            )
            lines.append(";\n")  # Add the semicolon and spacing

        lines.append("-- End of solution\n")
        solution_template = "\n".join(lines)

        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(PACKAGE_EVAL_TESTS_FILENAME, encrypted_eval_tests)
            zip_file.writestr(PACKAGE_SAMPLE_TESTS_FILENAME, encrypted_sample_tests)
            zip_file.writestr("solution.sql", solution_template)

            # Add run_testcase if present
            if RUN_TESTCASE_EXECUTABLE_PATH.exists():
                zip_file.writestr(
                    "run_testcase", RUN_TESTCASE_EXECUTABLE_PATH.read_bytes()
                )

            if pdf_content:
                zip_file.writestr("questions.pdf", pdf_content)

        zip_buffer.seek(0)
        return True, zip_buffer.getvalue(), None

    except Exception as e:
        logger.exception("Failed to create package")
        return False, None, f"Failed to create package: {e}"


def create_tests_artifacts(
    payload: Dict[str, Any],
) -> TestsArtifactsResult:
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
    if "queries" in payload and isinstance(payload.get("queries"), list):
        queries_list = payload["queries"]
        items_obj = {f"q{i + 1}": item for i, item in enumerate(queries_list)}
    else:
        # Handle legacy formats
        EXCLUDED_KEYS = {"sample_db_credentials", "eval_db_credentials", "pdf_content"}
        items_obj = {k: v for k, v in payload.items() if k not in EXCLUDED_KEYS}

    if not items_obj:
        return False, None, "VALIDATION: No queries provided", 400

    # --- Generate tests ---
    try:
        # Narrow types for static checkers: get_db_config_from_payload returns Optional[Dict]
        sample_db_cfg = cast(DBConfig, sample_db_config)
        eval_db_cfg = cast(DBConfig, eval_db_config)
        sample_tests = generate_tests(items_obj, sample_db_cfg)
        eval_tests = generate_tests(items_obj, eval_db_cfg)
    except Exception as e:
        logger.exception("Failed to generate tests")
        return False, None, f"Failed to generate tests: {e}", 500

    # --- Persist artifacts ---
    try:
        SAMPLE_TESTS_JSON_PATH.write_text(
            json.dumps(sample_tests, indent=4), encoding="utf-8"
        )
        TESTS_JSON_PATH.write_text(json.dumps(eval_tests, indent=4), encoding="utf-8")
    except Exception as e:
        return False, None, f"Failed to write test artifacts: {e}", 500

    # --- Generate Key (if needed) & Build Executables ---
    try:
        get_or_create_key(KEY_PATH)
    except Exception as e:
        return False, None, f"Failed to create/load encryption key: {e}", 500

    build_success, build_message, executable_path = build_student_executable()
    list_scores_success, list_scores_message, list_scores_path = (
        build_list_scores_executable()
    )

    response_data = {
        FieldNames.SAMPLE_TESTS: sample_tests,
        FieldNames.EVAL_TESTS: eval_tests,
        FieldNames.BUILD_STATUS: {
            FieldNames.SUCCESS: build_success,
            FieldNames.MESSAGE: build_message,
            FieldNames.EXECUTABLE_READY: executable_path is not None,
        },
        FieldNames.LIST_SCORES_STATUS: {
            FieldNames.SUCCESS: list_scores_success,
            FieldNames.MESSAGE: list_scores_message,
            FieldNames.EXECUTABLE_READY: list_scores_path is not None,
            FieldNames.EXECUTABLE_PATH: list_scores_path,
        },
    }

    return True, response_data, None, 200
