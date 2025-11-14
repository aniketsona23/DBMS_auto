#!/usr/bin/env python3
"""
test_generator.py

Test generation logic for different query types.
Handles SELECT, CREATE TABLE, CREATE FUNCTION, DML queries, etc.
"""
import re


def check_constraints(query, item):
    """
    Check if query violates any specified constraints.

    Args:
        query: SQL query string
        item: Test item dict with constraint flags

    Returns:
        List of violated constraint names
    """
    violations = []
    if item.get("require_join") and not re.search(r"\bJOIN\b", query, flags=re.I):
        violations.append("require_join")
    if item.get("forbid_join") and re.search(r"\bJOIN\b", query, flags=re.I):
        violations.append("forbid_join")
    nested = len(re.findall(r"\(\s*select\b", query, flags=re.I))
    if item.get("require_nested_select") and nested == 0:
        violations.append("require_nested_select")
    if item.get("forbid_nested_select") and nested > 0:
        violations.append("forbid_nested_select")
    # GROUP BY constraints
    has_group = re.search(r"\bGROUP\s+BY\b", query, flags=re.I) is not None
    if item.get("require_group_by") and not has_group:
        violations.append("require_group_by")
    if item.get("forbid_group_by") and has_group:
        violations.append("forbid_group_by")
    # ORDER BY constraints
    has_order = re.search(r"\bORDER\s+BY\b", query, flags=re.I) is not None
    if item.get("require_order_by") and not has_order:
        violations.append("require_order_by")
    if item.get("forbid_order_by") and has_order:
        violations.append("forbid_order_by")
    return violations


def extract_table_name(query):
    """Extract table name from CREATE/ALTER/DROP TABLE statement."""
    # match CREATE TABLE / ALTER TABLE / DROP TABLE `schema`.`tbl` or tbl
    m = re.search(
        r"\b(?:CREATE|ALTER|DROP)\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:`?([\w$]+)`?\.)?`?([\w$]+)`?",
        query,
        flags=re.I,
    )
    if m:
        return m.group(2) or m.group(1)
    # fallback simple match after keywords
    m2 = re.search(r"\b(?:CREATE|ALTER|DROP)\s+TABLE\s+`?([\w$]+)`?", query, flags=re.I)
    if m2:
        return m2.group(1)
    return None


def extract_function_name(query):
    """Extract function name from CREATE FUNCTION statement."""
    m = re.search(
        r"\bCREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+`?([\w$]+)`?",
        query,
        flags=re.I,
    )
    if m:
        return m.group(1)
    return None


def extract_view_name(query):
    """Extract view name from CREATE VIEW statement."""
    m = re.search(
        r"\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+`?([\w$]+)`?",
        query,
        flags=re.I,
    )
    if m:
        return m.group(1)
    return None


def extract_dml_table_name(query):
    """Extract table name from INSERT/UPDATE/DELETE statement."""
    m = re.search(
        r"\b(?:INTO|UPDATE)\s+`?(?:[\w$]+`?\.)?`?([\w$]+)`?", query, flags=re.I
    )
    if m:
        return m.group(1)
    return None


def sql_literal(value):
    """Convert Python value to SQL literal string."""
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    # escape single quotes
    s = str(value).replace("'", "\\'")
    return f"'{s}'"


def generate_test_for_select(query, item, cursor):
    """
    Generate test for SELECT query.

    Args:
        query: SQL query
        item: Test item dict
        cursor: Database cursor (unused for SELECT)

    Returns:
        Test JSON dict
    """
    # For SELECT queries, keep query as-is; do not execute
    return {"query": query}


def generate_test_for_table_ddl(query, item, cursor):
    """
    Generate test for CREATE/ALTER/DROP TABLE.

    Creates a DESCRIBE test_query and captures table structure.
    """
    tbl = extract_table_name(query)
    if not tbl:
        return {"expected_output": []}

    test_q = f"DESCRIBE `{tbl}`;"
    result = {"test_query": test_q}

    # Drop table if exists to avoid conflicts
    try:
        if "CREATE" in query.upper():
            cursor.execute(f"DROP TABLE IF EXISTS `{tbl}`")
    except Exception:
        pass

    # Execute the DDL
    try:
        cursor.execute(query)
        cursor.connection.commit()  # Commit the DDL
    except Exception as e:
        result["expected_output"] = []
        result["error"] = f"Failed to execute DDL: {e}"
        return result

    # Capture table structure
    try:
        cursor.execute(test_q)
        rows = cursor.fetchall()
        jsrows = [[str(c) if c is not None else "" for c in r] for r in rows]
        result["expected_output"] = jsrows
    except Exception as e:
        result["expected_output"] = []
        result["error"] = f"Failed to describe table: {e}"

    return result


def generate_test_for_function(query, item, cursor):
    """
    Generate test for CREATE FUNCTION.

    Creates SELECT func(args) test queries for provided test_inputs.
    """
    func = extract_function_name(query)

    # Drop function if exists
    if func:
        try:
            cursor.execute(f"DROP FUNCTION IF EXISTS `{func}`")
        except Exception:
            pass

    # Execute CREATE FUNCTION
    try:
        cursor.execute(query)
        cursor.connection.commit()  # Commit the function creation
    except Exception as e:
        return {"function_tests": [], "error": f"Failed to create function: {e}"}

    test_inputs = item.get("test_inputs") or item.get("test_params")
    if not func or not isinstance(test_inputs, list) or len(test_inputs) == 0:
        # No test inputs provided, return empty tests
        return {"function_tests": []}

    # Generate test cases for each input set
    results = []
    for args in test_inputs:
        if isinstance(args, dict) and "args" in args:
            argv = args["args"]
        elif isinstance(args, list):
            argv = args
        else:
            # single scalar
            argv = [args]

        arglist = ",".join(sql_literal(a) for a in argv)
        test_q = f"SELECT {func}({arglist}) as result;"

        try:
            cursor.execute(test_q)
            rows = cursor.fetchall()
            jsrows = [[str(c) if c is not None else "" for c in r] for r in rows]
            results.append({"test_query": test_q, "expected_output": jsrows})
        except Exception as e:
            results.append(
                {"test_query": test_q, "expected_output": [], "error": str(e)}
            )

    return {"function_tests": results}


def generate_test_for_view(query, item, cursor):
    """
    Generate test for CREATE VIEW.

    Creates a DESCRIBE test_query to validate view structure,
    and executes SELECT * from the view to capture sample data.
    Always returns a valid test_query regardless of execution success.
    """
    view_name = extract_view_name(query)
    if not view_name:
        # Still provide a placeholder test_query
        return {
            "test_query": "-- View name could not be extracted from query",
            "expected_output": [],
            "error": "Failed to extract view name from CREATE VIEW statement",
        }

    # Always set the test_query - this is the key part
    describe_query = f"DESCRIBE `{view_name}`;"
    result = {"test_query": describe_query, "expected_output": []}

    # Try to drop existing view first to avoid conflicts
    try:
        cursor.execute(f"DROP VIEW IF EXISTS `{view_name}`")
    except Exception:
        pass

    # Execute CREATE VIEW
    view_created = False
    try:
        cursor.execute(query)
        cursor.connection.commit()  # Commit the view creation
    except Exception as e:
        # View creation failed - still return test_query with empty expected_output
        result["error"] = f"Failed to create view during test generation: {e}"
        result["expected_output"] = []
        return result

    # Test 1: DESCRIBE to verify view structure
    try:
        cursor.execute(describe_query)
        rows = cursor.fetchall()
        jsrows = [[str(c) if c is not None else "" for c in r] for r in rows]
        result["expected_output"] = jsrows
    except Exception as e:
        result["expected_output"] = []
        result["error"] = f"Failed to describe view: {e}"
        return result

    # Test 2: SELECT * to verify view data (optional validation)
    return result


def generate_test_for_dml(query, item, cursor):
    """
    Generate test for INSERT/UPDATE/DELETE.

    Executes the DML and creates SELECT test_query to capture resulting data.
    """
    # Execute the DML statement
    try:
        cursor.execute(query)
        cursor.connection.commit()  # Commit the DML
    except Exception as e:
        return {"expected_output": [], "error": f"Failed to execute DML: {e}"}

    # Use provided test_query or infer one
    validation_sql = item.get("test_query") or item.get("validation_sql")

    if validation_sql:
        try:
            cursor.execute(validation_sql)
            rows = cursor.fetchall()
            jsrows = [[str(c) if c is not None else "" for c in r] for r in rows]
            return {"test_query": validation_sql, "expected_output": jsrows}
        except Exception as e:
            return {
                "test_query": validation_sql,
                "expected_output": [],
                "error": f"validation failed: {e}",
            }
    else:
        # Try to infer table name and select all
        tbl = extract_dml_table_name(query)
        if tbl:
            test_q = f"SELECT * FROM `{tbl}` LIMIT 100;"
            try:
                cursor.execute(test_q)
                rows = cursor.fetchall()
                jsrows = [[str(c) if c is not None else "" for c in r] for r in rows]
                return {"test_query": test_q, "expected_output": jsrows}
            except Exception as e:
                return {
                    "test_query": test_q,
                    "expected_output": [],
                    "error": f"infer select failed: {e}",
                }
        else:
            return {"expected_output": []}


def generate_test_for_query(query, qtype, item, cursor):
    """
    Generate test JSON for a query based on its type.

    Args:
        query: SQL query string
        qtype: Query type (select, function, ddl_dml, etc.)
        item: Original test item dict
        cursor: Database cursor

    Returns:
        Dict with test data (test_query, expected_output, etc.)
    """
    qtype = (qtype or "").strip().lower()

    try:
        # 1. CREATE / ALTER / DROP TABLE: route to DDL
        if re.search(r"\b(?:CREATE|ALTER|DROP)\s+TABLE\b", query, flags=re.I):
            return generate_test_for_table_ddl(query, item, cursor)

        # 2. CREATE VIEW: route to view logic
        elif qtype == "view" or re.search(
            r"\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\b", query, flags=re.I
        ):
            return generate_test_for_view(query, item, cursor)

        # 3. CREATE FUNCTION: route to function logic
        elif qtype == "function" or re.search(
            r"\bCREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\b", query, flags=re.I
        ):
            return generate_test_for_function(query, item, cursor)

        # 4. INSERT/UPDATE/DELETE: route to DML logic
        elif qtype in ["ddl_dml", "dml"] or re.search(
            r"\b(?:INSERT|UPDATE|DELETE)\b", query, flags=re.I
        ):
            return generate_test_for_dml(query, item, cursor)

        # 5. SELECT: only now handle select queries
        elif qtype == "select" or re.search(r"^\s*SELECT\b", query, flags=re.I):
            return generate_test_for_select(query, item, cursor)

        # 6. fallback: try to just run it, but don't error if fails
        else:
            try:
                cursor.execute(query)
                cursor.connection.commit()
            except Exception:
                pass
            return {"expected_output": []}

    except Exception as e:
        return {"expected_output": [], "error": str(e)}
