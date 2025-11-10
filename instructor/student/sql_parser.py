#!/usr/bin/env python3
"""
sql_parser.py

Simple SQL script parser that mirrors the behavior of the C++ `sql_parser.cpp`:
- supports DELIMITER changes
- splits into statements respecting the delimiter
- classifies statements into types: function, view, trigger, procedure, ddl_dml, select, unknown

Provides a simple function `parse_sql(script_text)` that returns a list of
dicts:{"query": ..., "type": ...}
"""
import re
import json
from typing import List, Dict


def analyze_query_type(query: str) -> str:
    clean = re.sub(r"--.*$", "", query, flags=re.MULTILINE)
    clean = re.sub(r"\s+", " ", clean)

    def has(pat):
        return re.search(pat, clean, flags=re.IGNORECASE) is not None

    if has(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\b"):
        return "function"
    if has(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\b"):
        return "view"
    if has(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\b"):
        return "trigger"
    if has(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\b"):
        return "procedure"
    if has(r"\bCREATE\b"):
        return "ddl_dml"
    if has(r"\bINSERT\b") or has(r"\bUPDATE\b") or has(r"\bDELETE\b"):
        return "ddl_dml"
    if has(r"\bSELECT\b"):
        return "select"
    return "unknown"


def parse_sql(script: str) -> List[Dict[str, str]]:
    if script is None:
        return []
    # normalize newlines
    content = script.replace("\r\n", "\n").replace("\r", "\n")
    lines = content.split("\n")
    queries: List[str] = []
    delimiter = ";"
    current = ""
    for raw in lines:
        line = raw.strip()
        upper = line.upper()

        # Skip comment-only lines
        if line.startswith("--") or line.startswith("#"):
            continue

        # Handle DELIMITER command
        if upper.startswith("DELIMITER"):
            # flush
            t = current.strip()
            if t:
                queries.append(t)
            elif current:  # If current has content but strips to empty, still count it
                queries.append("")  # Empty query placeholder
            current = ""
            parts = raw.split(None, 1)
            if len(parts) > 1:
                # Get the new delimiter and strip whitespace
                new_delim = parts[1].strip()
                # Handle cases like "DELIMITER / /" which should become "//"
                delimiter = new_delim.replace(" ", "")
            else:
                delimiter = ";"
            continue

        # Remove inline comments from the line
        # Handle -- comments
        comment_idx = raw.find("--")
        if comment_idx != -1:
            # Check if -- is not inside a string literal
            before_comment = raw[:comment_idx]
            # Simple check: count single quotes before comment
            if (
                before_comment.count("'") % 2 == 0
                and before_comment.count('"') % 2 == 0
            ):
                raw = raw[:comment_idx]

        # Handle # comments
        comment_idx = raw.find("#")
        if comment_idx != -1:
            before_comment = raw[:comment_idx]
            if (
                before_comment.count("'") % 2 == 0
                and before_comment.count('"') % 2 == 0
            ):
                raw = raw[:comment_idx]

        # Check if line is just a delimiter (e.g., a single ";")
        # This represents an empty/skipped query
        stripped_line = raw.strip()
        if stripped_line == delimiter:
            # Student wrote just ";" - they skipped this question
            queries.append("")  # Add empty query
            current = ""
            continue

        # Skip if line is empty after removing comments
        if not raw.strip():
            continue

        # append the raw line (keep original spacing inside)
        current += raw + "\n"
        trimmed = current.rstrip()
        if len(trimmed) >= len(delimiter) and trimmed.endswith(delimiter):
            # Remove the delimiter from the end
            final = trimmed[: len(trimmed) - len(delimiter)].strip()
            # Always append, even if empty (represents skipped question)
            queries.append(final)
            current = ""

    # Handle any remaining content
    if current.strip():
        final = current.strip()
        # Remove delimiter if it's at the end
        if delimiter and len(final) >= len(delimiter) and final.endswith(delimiter):
            final = final[: len(final) - len(delimiter)].strip()
        queries.append(final)
    elif current:  # Has content but strips to empty
        queries.append("")

    out = []
    for q in queries:
        # For empty queries, mark as "missing" or "unknown" type
        if not q or q.strip() == "":
            out.append({"query": "", "type": "missing"})
        else:
            out.append({"query": q, "type": analyze_query_type(q)})
    return out


if __name__ == "__main__":
    import sys

    text = sys.stdin.read() if sys.stdin and not sys.stdin.isatty() else ""
    if len(sys.argv) >= 2:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            text = f.read()
    res = parse_sql(text)
    print(json.dumps(res, indent=2))
