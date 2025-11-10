"""
core package

Core business logic for SQL parsing and test generation.
"""
from .sql_parser import parse_sql
from .test_generator import check_constraints, generate_test_for_query

__all__ = [
    'parse_sql',
    'check_constraints',
    'generate_test_for_query',
]
