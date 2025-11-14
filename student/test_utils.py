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

try:
    from cryptography.fernet import Fernet  # type: ignore
except ImportError:  # pragma: no cover
    Fernet = None  # type: ignore


# ------------------------- Result Helpers ------------------------- #
def make_result(
    test_key: str,
    test_data: Dict[str, Any],
    status: str,
    message: str,
    score_mult: float,
    **extra: Any,
) -> Dict[str, Any]:
    max_score = test_data.get("score", 1)
    score = max_score * score_mult
    return {
        "test": test_key,
        "status": status,
        "message": message,
        "score": score,
        "max_score": max_score,
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
    print(f"\nTesting {test_key}:")
    print(f"Query: {student_query[:200]}{'...' if len(student_query) > 200 else ''}")
    print("-" * 60)


def violates_constraints(student_query: str, test: Dict[str, Any]) -> str:
    q = student_query.lower()
    if test.get("forbid_join") and re.search(r"\bjoin\b", q, re.I):
        return "forbid_join"
    if test.get("require_join") and not re.search(r"\bjoin\b", q, re.I):
        return "require_join"
    if test.get("require_nested_select") and not re.search(
        r"\([ \t\n\r]*select", q, re.I
    ):
        return "require_nested_select"
    if test.get("forbid_nested_select") and re.search(r"\([ \t\n\r]*select", q, re.I):
        return "forbid_nested_select"
    if test.get("forbid_group_by") and re.search(r"\bgroup\s+by\b", q, re.I):
        return "forbid_group_by"
    if test.get("require_group_by") and not re.search(r"\bgroup\s+by\b", q, re.I):
        return "require_group_by"
    if test.get("forbid_order_by") and re.search(r"\border\s+by\b", q, re.I):
        return "forbid_order_by"
    if test.get("require_order_by") and not re.search(r"\border\s+by\b", q, re.I):
        return "require_order_by"
    return ""


# ------------------------- Encryption / Packaging ------------------------- #
def load_and_decrypt_tests(
    encrypted_path: Path, encryption_key: bytes, crypto_available: bool
) -> Dict[str, Any]:
    if not encryption_key:
        raise Exception("Encryption key not set.")
    if not crypto_available or Fernet is None:
        raise Exception("Cryptography library not available.")
    try:
        encrypted_data = encrypted_path.read_bytes()
        fernet = Fernet(encryption_key)
        decrypted = fernet.decrypt(encrypted_data)
        return json.loads(decrypted.decode("utf-8"))
    except Exception as e:  # pragma: no cover - error path
        raise Exception(f"Failed to decrypt tests: {e}")


def save_encrypted_report_and_zip(
    results: Dict[str, Any],
    solution_path: Path,
    student_id: str,
    encryption_key: bytes,
    crypto_available: bool,
) -> None:
    encrypted_report_name = f"{student_id}_results.json.enc"
    encrypted_report_path = Path.cwd() / encrypted_report_name
    if not (crypto_available and encryption_key and Fernet):
        print("Skipping encryption: cryptography or key unavailable.")
        return
    try:
        questions = {
            tr.get("test", ""): (
                "Pass"
                if tr.get("status") == "PASS"
                else (tr.get("message") or tr.get("status") or "FAIL")
            )
            for tr in results.get("test_results", [])
        }
        payload = {
            "student_id": student_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_score": results.get("total_score", 0),
            "questions": questions,
        }
        fernet = Fernet(encryption_key)
        encrypted_data = fernet.encrypt(json.dumps(payload, indent=2).encode("utf-8"))
        encrypted_report_path.write_bytes(encrypted_data)
        print(f"Encrypted results saved: {encrypted_report_path.name}")
    except Exception as e:
        print(f"Failed to create encrypted results: {e}")
        return
    # ZIP
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


# ------------------------- Printing ------------------------- #
def print_results(results: Dict[str, Any]) -> None:
    def supports_color():
        import sys as _sys

        return hasattr(_sys.stdout, "isatty") and _sys.stdout.isatty()

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

    for r in results.get("test_results", []):
        test_key = r.get("test", "?")
        status = r.get("status", "UNKNOWN")
        msg = r.get("message", "")
        score = r.get("score", 0)
        max_score = r.get("max_score", 1)
        student_query = r.get("student_query", "")

        if status == "PASS":
            indicator, status_line = f"{GREEN}✓{RESET}", f"{GREEN}{status}{RESET}"
        elif status == "FAIL":
            indicator, status_line = f"{RED}✗{RESET}", f"{RED}{status}{RESET}"
        elif status in ("ERROR", "WARNING"):
            indicator, status_line = f"{YELLOW}⚠{RESET}", f"{YELLOW}{status}{RESET}"
        else:
            indicator, status_line = "?", status

        print(f"\n{indicator} {test_key}: {status_line} ({score}/{max_score} points)")
        if student_query:
            query_display = (
                student_query[:150] + "..."
                if len(student_query) > 150
                else student_query
            )
            print(f"   Query: {query_display}")
        print(f"   {msg}")
        if "failures" in r:
            for failure in r["failures"]:
                print(f"     - {failure}")

    total = results.get("total_score", 0)
    max_s = results.get("max_score", 0)
    perc = results.get("percentage", 0.0)
    color = GREEN if total == max_s and max_s > 0 else RED
    print("\n" + "=" * 70)
    print(f"FINAL SCORE: {color}{total}{RESET}/{max_s} ({perc:.2f}%){RESET}")
    print("=" * 70 + "\n")
