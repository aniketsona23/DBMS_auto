#!/usr/bin/env python3
"""
handlers.py

HTTP request handlers for the test generation server.
"""

import json
import logging
import mimetypes
import os
from typing import Any, Tuple
from shared.constants import (
    REPO_PATH,
    INSTRUCTOR_PUBLIC_DIR,
    LIST_SCORES_EXECUTABLE_PATH,
    TESTS_JSON_PATH,
    SAMPLE_TESTS_JSON_PATH,
)
from shared.db_utils import (
    get_db_connection,
    reset_database_via_cli,
)
from shared.sql_parser import parse_sql
from instructor.utils.utils import (
    extract_multipart_data,
    get_db_config_from_payload,
    parse_json_body,
)
from instructor.api.services import create_student_package, create_tests_artifacts

MIME_JSON = "application/json"
MIME_TEXT = "text/plain"
MIME_ZIP = "application/zip"
MIME_OCTET = "application/octet-stream"
logger = logging.getLogger(__name__)


def handle_parse(body: bytes, content_type: str) -> Tuple[int, Any, str]:
    """Parse SQL script and return queries."""
    sql_text = ""

    if MIME_JSON in content_type:
        payload, error = parse_json_body(body)
        if error:
            return 400, error, MIME_TEXT
        sql_text = payload.get("sql", "") if isinstance(payload, dict) else ""
    else:
        try:
            sql_text = body.decode("utf-8")
        except UnicodeDecodeError:
            sql_text = ""

    if not sql_text:
        return 400, "No SQL provided", MIME_TEXT

    try:
        items = parse_sql(sql_text)
        return 200, json.dumps(items, indent=2), MIME_JSON
    except Exception as e:
        logger.error(f"SQL Parse Error: {e}")
        return 500, f"Parser error: {e}", MIME_TEXT


def handle_reset_db(body: bytes, content_type: str) -> Tuple[int, Any, str]:
    """Run SQL via mysql CLI."""
    if MIME_JSON not in content_type:
        return 400, "Content-Type must be application/json", MIME_TEXT

    payload, error = parse_json_body(body)
    if error:
        return 400, error, MIME_TEXT
    if not isinstance(payload, dict):
        return 400, "Invalid JSON payload", MIME_TEXT

    sql_text = payload.get("sql", "")
    if not sql_text:
        return 400, "No SQL provided in payload ('sql' key)", MIME_TEXT

    db_config, err = get_db_config_from_payload(payload, key_name="db_credentials")
    if err:
        return 400, err, MIME_TEXT

    success, output = reset_database_via_cli(sql_text, db_config, str(REPO_PATH))
    return (200 if success else 500), output, MIME_TEXT


def handle_test_connection(body: bytes) -> Tuple[int, Any, str]:
    """Test database connection."""
    payload, error = parse_json_body(body)
    if error:
        return 400, error, MIME_TEXT
    if not isinstance(payload, dict):
        return 400, "Invalid JSON payload", MIME_TEXT

    db_config, err = get_db_config_from_payload(payload, key_name=None)
    if err:
        return 400, err, MIME_TEXT

    try:
        with get_db_connection(db_config) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
        return 200, "Connection successful", MIME_TEXT
    except Exception as e:
        logger.error(f"DB Connection failed: {e}")
        return 500, f"Connection failed: {str(e)}", MIME_TEXT


def handle_create_tests(body: bytes) -> Tuple[int, Any, str]:
    """Delegates to service layer to create tests."""
    payload, error = parse_json_body(body)
    if error:
        return 400, error, MIME_TEXT
    if not isinstance(payload, dict):
        return 400, "Invalid JSON payload", MIME_TEXT

    ok, data, err, status = create_tests_artifacts(payload)
    if not ok:
        return status, (err or "Failed to create tests"), MIME_TEXT

    return 200, json.dumps(data, indent=2), MIME_JSON


def handle_static_file(path: str) -> Tuple[int, Any, str]:
    """Serve static files safely."""
    rel = "index.html" if path == "/" else path.lstrip("/")

    # Secure path resolution
    abs_web_dir = os.path.abspath(str(INSTRUCTOR_PUBLIC_DIR))
    requested = os.path.abspath(os.path.join(abs_web_dir, rel))

    # Security check: ensure requested path is inside WEB_DIR
    if not requested.startswith(abs_web_dir):
        return 403, "Forbidden", MIME_TEXT

    if os.path.isdir(requested):
        requested = os.path.join(requested, "index.html")

    if not os.path.exists(requested):
        return 404, "Not found", MIME_TEXT

    try:
        with open(requested, "rb") as f:
            data = f.read()

        ctype, _ = mimetypes.guess_type(requested)
        return 200, data, (ctype or MIME_OCTET)
    except Exception as e:
        logger.error(f"Static file error: {e}")
        return 500, f"Failed to read file: {e}", MIME_TEXT


def handle_download_list_scores() -> Tuple[int, Any, str]:
    """Download the list_scores executable."""

    if not LIST_SCORES_EXECUTABLE_PATH.exists():
        return (
            404,
            "list_scores executable not found. Run create-tests first.",
            MIME_TEXT,
        )

    try:
        with open(LIST_SCORES_EXECUTABLE_PATH, "rb") as f:
            data = f.read()
        return 200, data, MIME_OCTET
    except Exception as e:
        logger.error(f"Failed to read list_scores: {e}")
        return 500, f"Failed to read executable: {e}", MIME_TEXT


def handle_create_package(body: bytes, content_type: str) -> Tuple[int, Any, str]:
    """Create encrypted zip package for students."""
    db_credentials = None
    pdf_content = None

    if "multipart/form-data" in content_type:
        db_credentials, pdf_content = extract_multipart_data(body, content_type)

    # Check for artifacts existence
    if not TESTS_JSON_PATH.exists() or not SAMPLE_TESTS_JSON_PATH.exists():
        return 400, "Required test artifacts missing. Create tests first.", MIME_TEXT

    try:
        # Read files
        with open(TESTS_JSON_PATH, "r", encoding="utf-8") as f:
            eval_tests_content = f.read()
        with open(SAMPLE_TESTS_JSON_PATH, "r", encoding="utf-8") as f:
            sample_tests_content = f.read()

        ok, zip_bytes, err = create_student_package(
            eval_tests_content=eval_tests_content,
            sample_tests_content=sample_tests_content,
            db_credentials=db_credentials,
            pdf_content=pdf_content,
        )

        if not ok or zip_bytes is None:
            return 500, (err or "Failed to create package"), MIME_TEXT

        return 200, zip_bytes, MIME_ZIP
    except Exception as e:
        logger.exception("Package creation failed")
        return 500, f"Failed to create package: {e}", MIME_TEXT
