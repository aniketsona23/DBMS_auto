#!/usr/bin/env python3
"""
test_utils.py

Utility helpers for the student test runner to keep `run_testcase.py` lean.
Includes:
  - Result factory helpers
  - Query execution / normalization / comparison
  - Constraint checking
  - Decryption loader
  - Printing & packaging helpers
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple
from datetime import datetime

from shared.constants import RESULTS_FILENAME_TEMPLATE, FieldNames
from shared.logger import get_logger
from shared.encryption import encrypt_string, decrypt_data
from shared.models import (
    QuestionResult,
    create_results_payload,
    test_result_to_question_result,
)

logger = get_logger(__name__)


# ------------------------- Result Helpers ------------------------- #
def make_result(
    test_key: str,
    test_data: Dict[str, Any],
    status: str,
    message: str,
    score_mult: float,
    **extra: Any,
) -> Dict[str, Any]:
    max_score = test_data.get(FieldNames.SCORE, 1)
    score = max_score * score_mult
    return {
        FieldNames.TEST: test_key,
        FieldNames.STATUS: status,
        FieldNames.MESSAGE: message,
        FieldNames.SCORE: score,
        FieldNames.MAX_SCORE: max_score,
        **extra,
    }


def pass_result(
    test_key: str, test_data: Dict[str, Any], message: str, **extra: Any
) -> Dict[str, Any]:
    return make_result(test_key, test_data, "PASS", message, 1.0, **extra)


def fail_result(
    test_key: str, test_data: Dict[str, Any], message: str, **extra: Any
) -> Dict[str, Any]:
    return make_result(test_key, test_data, "FAIL", message, 0.0, **extra)


def error_result(
    test_key: str, test_data: Dict[str, Any], message: str, **extra: Any
) -> Dict[str, Any]:
    return make_result(test_key, test_data, "ERROR", message, 0.0, **extra)


def warning_result(
    test_key: str,
    test_data: Dict[str, Any],
    message: str,
    score_mult: float,
    **extra: Any,
) -> Dict[str, Any]:
    return make_result(test_key, test_data, "WARNING", message, score_mult, **extra)


def missing_result(
    test_key: str, test_data: Dict[str, Any], message: str, **extra: Any
) -> Dict[str, Any]:
    return make_result(test_key, test_data, "MISSING", message, 0.0, **extra)


# ------------------------- Query Helpers ------------------------- #
def normalize_output(rows: List[tuple]) -> List[List[str]]:
    return [[str(c) if c is not None else "" for c in row] for row in rows]


def compare_outputs(
    actual: List[List[str]], expected: List[List[str]]
) -> Tuple[bool, str]:
    if len(actual) != len(expected):
        return False, "Output mismatch"
    for i, (ar, er) in enumerate(zip(actual, expected)):
        if len(ar) != len(er):
            return False, "Output mismatch"
        for j, (av, ev) in enumerate(zip(ar, er)):
            try:
                av_num = float(av)
                ev_num = float(ev)
                if abs(av_num - ev_num) > 1e-6:
                    return False, "Output mismatch"
            except (ValueError, TypeError):
                if str(av) != str(ev):
                    return False, "Output mismatch"
    return True, ""


def execute_query(query: str, conn) -> Tuple[bool, Any]:
    try:
        with conn.cursor() as cursor:
            cursor.execute(query)
            results = cursor.fetchall()
        return True, results
    except Exception as e:  # pragma: no cover - error path
        return False, str(e)


def print_test_header(test_key: str, student_query: str) -> None:
    logger.info(f"Testing {test_key}:")


def violates_constraints(student_query: str, test: Dict[str, Any]) -> str:
    q = student_query.lower()
    if test.get(FieldNames.FORBID_JOIN) and re.search(r"\bjoin\b", q, re.I):
        return FieldNames.FORBID_JOIN
    if test.get(FieldNames.REQUIRE_JOIN) and not re.search(r"\bjoin\b", q, re.I):
        return FieldNames.REQUIRE_JOIN
    if test.get(FieldNames.REQUIRE_NESTED_SELECT) and not re.search(
        r"\([ \t\n\r]*select", q, re.I
    ):
        return FieldNames.REQUIRE_NESTED_SELECT
    if test.get(FieldNames.FORBID_NESTED_SELECT) and re.search(
        r"\([ \t\n\r]*select", q, re.I
    ):
        return FieldNames.FORBID_NESTED_SELECT
    if test.get(FieldNames.FORBID_GROUP_BY) and re.search(r"\bgroup\s+by\b", q, re.I):
        return FieldNames.FORBID_GROUP_BY
    if test.get(FieldNames.REQUIRE_GROUP_BY) and not re.search(
        r"\bgroup\s+by\b", q, re.I
    ):
        return FieldNames.REQUIRE_GROUP_BY
    if test.get(FieldNames.FORBID_ORDER_BY) and re.search(r"\border\s+by\b", q, re.I):
        return FieldNames.FORBID_ORDER_BY
    if test.get(FieldNames.REQUIRE_ORDER_BY) and not re.search(
        r"\border\s+by\b", q, re.I
    ):
        return FieldNames.REQUIRE_ORDER_BY
    return ""


# ------------------------- Encryption / Packaging ------------------------- #
def load_and_decrypt_tests(encrypted_path: Path, encryption_key: bytes) -> Dict:
    if not encryption_key:
        raise Exception("Encryption key not set.")
    try:
        encrypted_data = encrypted_path.read_bytes()
        decrypted = decrypt_data(encrypted_data, encryption_key)
        return json.loads(decrypted.decode("utf-8"))
    except Exception as e:  # pragma: no cover - error path
        raise Exception(f"Failed to load tests: {e}")


def save_encrypted_report_and_zip(
    results: Dict[str, Any],
    solution_path: Path,
    student_id: str,
    encryption_key: bytes,
) -> None:
    report_name = RESULTS_FILENAME_TEMPLATE.format(student_id=student_id)
    report_path = Path.cwd() / report_name
    if not encryption_key:
        logger.warning("Skipping encryption: encryption key not available.")
        return
    try:
        questions: Dict[str, QuestionResult] = {
            tr.get(FieldNames.TEST, ""): test_result_to_question_result(tr)
            for tr in results.get(FieldNames.TEST_RESULTS, [])
        }
        payload = create_results_payload(
            student_id=student_id,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total_score=results.get(FieldNames.TOTAL_SCORE, 0),
            max_score=results.get(FieldNames.MAX_SCORE, 0),
            questions=questions,
        )
        encrypted_data = encrypt_string(json.dumps(payload, indent=2), encryption_key)
        report_path.write_bytes(encrypted_data)
        logger.info(f"Encrypted results saved: {report_path.name}")
    except Exception as e:
        logger.error(f"Failed to create results: {e}")
        return
    # ZIP
    zip_path = Path.cwd() / f"{student_id}_submission.zip"
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if solution_path.exists():
                zf.write(solution_path, arcname="solution.sql")
            if report_path.exists():
                zf.write(report_path, arcname=report_path.name)
        logger.info(f"Submission ZIP created: {zip_path.name}")
        logger.info(f"Files inside: solution.sql, {report_path.name}")
    except Exception as e:
        logger.error(f"Failed to create submission zip: {e}")


# ------------------------- Printing ------------------------- #
def print_results(results: Dict[str, Any]) -> None:
    def supports_color():
        import sys as _sys

        return hasattr(_sys.stdout, "isatty") and _sys.stdout.isatty()

    GREEN = "\033[92m" if supports_color() else ""
    RED = "\033[91m" if supports_color() else ""
    YELLOW = "\033[93m" if supports_color() else ""
    RESET = "\033[0m" if supports_color() else ""

    logger.info("\n" + "=" * 70)
    logger.info("TEST RESULTS")
    logger.info("=" * 70)

    if "error" in results:
        logger.error(f"ERROR: {results['error']}")
        return

    for r in results.get(FieldNames.TEST_RESULTS, []):
        test_key = r.get(FieldNames.TEST, "?")
        status = r.get(FieldNames.STATUS, "UNKNOWN")
        msg = r.get(FieldNames.MESSAGE, "")
        score = r.get(FieldNames.SCORE, 0)
        max_score = r.get(FieldNames.MAX_SCORE, 1)
        student_query = r.get(FieldNames.STUDENT_QUERY, "")

        if status == FieldNames.STATUS_PASS:
            indicator, status_line = f"{GREEN}✓{RESET}", f"{GREEN}{status}{RESET}"
        elif status == FieldNames.STATUS_FAIL:
            indicator, status_line = f"{RED}✗{RESET}", f"{RED}{status}{RESET}"
        elif status in (FieldNames.STATUS_ERROR, FieldNames.STATUS_WARNING):
            indicator, status_line = f"{YELLOW}⚠{RESET}", f"{YELLOW}{status}{RESET}"
        else:
            indicator, status_line = "?", status

        logger.info(
            f"{indicator} {test_key}: {status_line} ({score}/{max_score} points)"
        )
        if student_query:
            query_display = (
                student_query[:150] + "..."
                if len(student_query) > 150
                else student_query
            )
            logger.info(f"   Query: {query_display}")
        logger.info(f"   {msg}")
        if FieldNames.FAILURES in r:
            for failure in r[FieldNames.FAILURES]:
                logger.info(f"     - {failure}")

    total = results.get(FieldNames.TOTAL_SCORE, 0)
    max_s = results.get(FieldNames.MAX_SCORE, 0)
    perc = results.get("percentage", 0.0)
    logger.info("\n" + "=" * 70)
    logger.info(f"FINAL SCORE: {total}/{max_s} ({perc:.2f}%)")
    logger.info("=" * 70 + "\n")
