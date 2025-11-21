#!/usr/bin/env python3
"""
test_generator.py

Test generation logic for different query types.
Handles SELECT, CREATE TABLE, CREATE FUNCTION, DML queries, etc.
"""

import re
import logging
from typing import Any, Dict, List, Optional

# --- Regex Constants (Compiled for Performance) ---
RE_JOIN = re.compile(r"\bJOIN\b", flags=re.I)
RE_GROUP_BY = re.compile(r"\bGROUP\s+BY\b", flags=re.I)
RE_ORDER_BY = re.compile(r"\bORDER\s+BY\b", flags=re.I)
RE_NESTED_SELECT = re.compile(r"\(\s*select\b", flags=re.I)

RE_TABLE_DDL = re.compile(
    r"\b(?:CREATE|ALTER|DROP)\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:`?([\w$]+)`?\.)?`?([\w$]+)`?",
    flags=re.I,
)
RE_SIMPLE_TABLE = re.compile(
    r"\b(?:CREATE|ALTER|DROP)\s+TABLE\s+`?([\w$]+)`?", flags=re.I
)

RE_CREATE_FUNC = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+`?([\w$]+)`?", flags=re.I
)
RE_CREATE_VIEW = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+`?([\w$]+)`?", flags=re.I
)
RE_DML_TABLE = re.compile(
    r"\b(?:INTO|UPDATE)\s+`?(?:[\w$]+`?\.)?`?([\w$]+)`?", flags=re.I
)

RE_SELECT_START = re.compile(r"^\s*SELECT\b", flags=re.I)
RE_DML_KEYWORDS = re.compile(r"\b(?:INSERT|UPDATE|DELETE)\b", flags=re.I)

logger = logging.getLogger(__name__)


def check_constraints(query: str, item: Dict[str, Any]) -> List[str]:
    """
    Check if query violates any specified constraints.
    Uses a data-driven approach to reduce code duplication.
    """
    violations = []

    # Rules format: (Constraint Name, Regex Pattern, Must Exist?)
    # Must Exist = True -> Require Check, False -> Forbid Check
    # If 'Require' flag is set, pattern MUST exist.
    # If 'Forbid' flag is set, pattern MUST NOT exist.

    simple_checks = [
        ("join", RE_JOIN),
        ("group_by", RE_GROUP_BY),
        ("order_by", RE_ORDER_BY),
    ]

    for base_name, pattern in simple_checks:
        found = pattern.search(query) is not None

        # Check Requirement
        req_key = f"require_{base_name}"
        if item.get(req_key) and not found:
            violations.append(req_key)

        # Check Forbidden
        forbid_key = f"forbid_{base_name}"
        if item.get(forbid_key) and found:
            violations.append(forbid_key)

    # Special case: Nested Select (Counts occurrences)
    nested_count = len(RE_NESTED_SELECT.findall(query))
    if item.get("require_nested_select") and nested_count == 0:
        violations.append("require_nested_select")
    if item.get("forbid_nested_select") and nested_count > 0:
        violations.append("forbid_nested_select")

    return violations


def extract_name(
    query: str, complex_re: re.Pattern, simple_re: Optional[re.Pattern] = None
) -> Optional[str]:
    """Generic extractor for names from SQL queries."""
    m = complex_re.search(query)
    if m:
        # Group 2 is usually table name in schema.table, Group 1 is schema or table
        return m.group(2) or m.group(1)

    if simple_re:
        m2 = simple_re.search(query)
        if m2:
            return m2.group(1)
    return None


def format_sql_rows(rows: List[tuple]) -> List[List[str]]:
    """Helper to ensure all DB results are strings for JSON serialization."""
    return [[str(c) if c is not None else "" for c in r] for r in rows]


def generate_test_for_select(
    query: str, item: Dict[str, Any], cursor: Any
) -> Dict[str, Any]:
    """Generate test for SELECT query."""
    return {"query": query}


def generate_test_for_table_ddl(
    query: str, item: Dict[str, Any], cursor: Any
) -> Dict[str, Any]:
    """Generate test for CREATE/ALTER/DROP TABLE."""
    tbl = extract_name(query, RE_TABLE_DDL, RE_SIMPLE_TABLE)
    if not tbl:
        return {"expected_output": [], "error": "Could not extract table name"}

    test_q = f"DESCRIBE `{tbl}`;"
    result: Dict[str, Any] = {"test_query": test_q}

    try:
        if "CREATE" in query.upper():
            cursor.execute(f"DROP TABLE IF EXISTS `{tbl}`")

        cursor.execute(query)
        cursor.connection.commit()

        # Capture structure
        cursor.execute(test_q)
        result["expected_output"] = format_sql_rows(cursor.fetchall())

    except Exception as e:
        result["expected_output"] = []
        result["error"] = f"DDL Execution failed: {str(e)}"

    return result


def generate_test_for_function(
    query: str, item: Dict[str, Any], cursor: Any
) -> Dict[str, Any]:
    """Generate test for CREATE FUNCTION."""
    func = extract_name(query, RE_CREATE_FUNC)
    if not func:
        return {"function_tests": [], "error": "Could not extract function name"}

    try:
        cursor.execute(f"DROP FUNCTION IF EXISTS `{func}`")
        cursor.execute(query)
        cursor.connection.commit()
    except Exception as e:
        return {"function_tests": [], "error": f"Failed to create function: {e}"}

    test_inputs = item.get("test_inputs") or item.get("test_params")
    if not isinstance(test_inputs, list) or not test_inputs:
        return {"function_tests": []}

    results: List[Dict[str, Any]] = []

    for args in test_inputs:
        # Extract arguments
        if isinstance(args, dict) and "args" in args:
            argv = args["args"]
        elif isinstance(args, list):
            argv = args
        else:
            argv = [args]

        # Use parameterization instead of string formatting for safety
        placeholders = ",".join(["%s"] * len(argv))

       

        # Safe construction for display/storage purposes (simplified for test gen)
        safe_args = [
            str(a) if isinstance(a, (int, float)) else f"'{str(a)}'" for a in argv
        ]
        display_q = f"SELECT {func}({','.join(safe_args)}) as result;"

        try:
            # Execute using parameters to be safe
            cursor.execute(f"SELECT {func}({placeholders})", argv)
            rows = cursor.fetchall()
            results.append(
                {"test_query": display_q, "expected_output": format_sql_rows(rows)}
            )
        except Exception as e:
            results.append(
                {"test_query": display_q, "expected_output": [], "error": str(e)}
            )

    return {"function_tests": results}


def generate_test_for_view(
    query: str, item: Dict[str, Any], cursor: Any
) -> Dict[str, Any]:
    """Generate test for CREATE VIEW."""
    view_name = extract_name(query, RE_CREATE_VIEW)
    if not view_name:
        return {
            "test_query": "-- Missing view name",
            "expected_output": [],
            "error": "Failed to extract view name",
        }

    describe_query = f"DESCRIBE `{view_name}`;"
    result: Dict[str, Any] = {"test_query": describe_query, "expected_output": []}

    try:
        cursor.execute(f"DROP VIEW IF EXISTS `{view_name}`")
        cursor.execute(query)
        cursor.connection.commit()

        cursor.execute(describe_query)
        result["expected_output"] = format_sql_rows(cursor.fetchall())
    except Exception as e:
        result["error"] = f"View generation failed: {str(e)}"

    return result


def generate_test_for_dml(
    query: str, item: Dict[str, Any], cursor: Any
) -> Dict[str, Any]:
    """Generate test for INSERT/UPDATE/DELETE."""
    try:
        cursor.execute(query)
        cursor.connection.commit()
    except Exception as e:
        return {"expected_output": [], "error": f"DML Failed: {e}"}

    validation_sql = item.get("test_query") or item.get("validation_sql")

    if validation_sql:
        try:
            cursor.execute(validation_sql)
            return {
                "test_query": validation_sql,
                "expected_output": format_sql_rows(cursor.fetchall()),
            }
        except Exception as e:
            return {
                "test_query": validation_sql,
                "expected_output": [],
                "error": f"Validation SQL failed: {e}",
            }

    # Infer SELECT if no validation provided
    tbl = extract_name(query, RE_DML_TABLE)
    if tbl:
        test_q = f"SELECT * FROM `{tbl}` LIMIT 100;"
        try:
            cursor.execute(test_q)
            return {
                "test_query": test_q,
                "expected_output": format_sql_rows(cursor.fetchall()),
            }
        except Exception as e:
            return {
                "test_query": test_q,
                "expected_output": [],
                "error": f"Inferred select failed: {e}",
            }

    return {"expected_output": []}


def generate_test_for_query(
    query: str, qtype: str, item: Dict[str, Any], cursor: Any
) -> Dict[str, Any]:
    """
    Dispatcher function to generate test JSON based on query type.
    """
    qtype = (qtype or "").strip().lower()

    try:
        # 1. DDL (Tables)
        if RE_TABLE_DDL.search(query):
            return generate_test_for_table_ddl(query, item, cursor)

        # 2. Views
        if qtype == "view" or RE_CREATE_VIEW.search(query):
            return generate_test_for_view(query, item, cursor)

        # 3. Functions
        if qtype == "function" or RE_CREATE_FUNC.search(query):
            return generate_test_for_function(query, item, cursor)

        # 4. DML
        if qtype in ["ddl_dml", "dml"] or RE_DML_KEYWORDS.search(query):
            return generate_test_for_dml(query, item, cursor)

        # 5. SELECT
        if qtype == "select" or RE_SELECT_START.search(query):
            return generate_test_for_select(query, item, cursor)

        # 6. Fallback: Execute blind
        try:
            cursor.execute(query)
            cursor.connection.commit()
        except Exception:
            pass
        return {"expected_output": []}

    except Exception as e:
        return {"expected_output": [], "error": str(e)}
