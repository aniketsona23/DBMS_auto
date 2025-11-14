#!/usr/bin/env python3
"""
utils.py

Shared helper utilities for handler payload validation and common operations.
"""

import json
import logging
from typing import Optional, Tuple, Dict, Any
import re

logger = logging.getLogger(__name__)


def get_db_config_from_payload(
    payload: Dict[str, Any], key_name: Optional[str] = None
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Extract and validate DB credentials from a JSON payload.

    If `key_name` is provided, validate `payload[key_name]` as the credentials
    object. If `key_name` is None, validate `payload` itself as the credentials
    object.

    Returns (db_config_dict, error_message). On success, error_message is None.
    Required keys: host, port, user, password, database.
    """
    if not isinstance(payload, dict):
        return None, "Payload must be a JSON object"

    creds = payload.get(key_name) if key_name else payload
    if not isinstance(creds, dict):
        if key_name:
            return None, f"Missing or invalid '{key_name}' in payload"
        return None, "Missing or invalid DB credential object in payload"

    required = ["host", "port", "user", "password", "database"]
    missing = [k for k in required if creds.get(k) is None]
    if missing:
        return None, f"Missing DB credential keys: {', '.join(missing)}"

    return {k: creds.get(k) for k in required}, None


def sort_key_numeric(key: str) -> int:
    """Extract first integer occurrence from a string for numeric sorting.

    Returns the integer if found, else 0. Useful for sorting keys like
    'q1', 'q2', ... 'q10' numerically.
    """
    match = re.search(r"\d+", key or "")
    return int(match.group()) if match else 0


def extract_multipart_data(
    body: bytes, content_type: str
) -> Tuple[Optional[Dict], Optional[bytes]]:
    """
    A basic manual extractor for multipart data.
    Note: In production, use `email.message_from_bytes` or `requests_toolbelt`.
    This cleans up the logic but remains a basic implementation.
    """
    try:
        # Handle boundary parameter potentially being quoted
        boundary_part = content_type.split("boundary=")[1]
        boundary = boundary_part.strip('"').encode()

        parts = body.split(b"--" + boundary)

        db_creds = None
        pdf_bytes = None

        for part in parts:
            if b'name="db_credentials"' in part:
                header_end = part.find(b"\r\n\r\n")
                if header_end != -1:
                    json_bytes = part[header_end + 4 :].rstrip(b"\r\n")
                    if json_bytes:
                        db_creds = json.loads(json_bytes.decode("utf-8"))

            elif b'name="questions_pdf"' in part:
                header_end = part.find(b"\r\n\r\n")
                if header_end != -1:
                    pdf_bytes = part[header_end + 4 :].rstrip(b"\r\n")

        return db_creds, pdf_bytes
    except Exception as e:
        logger.error(f"Multipart parsing failed: {e}")
        return None, None


def parse_json_body(body: bytes) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Helper to decode and load JSON body.
    Returns: (payload, error_message)
    """
    if not body:
        return {}, None
    try:
        return json.loads(body.decode("utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return None, f"Invalid JSON format: {str(e)}"
