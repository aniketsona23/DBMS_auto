"""
models.py

Centralized data structures and models for the DBMS test runner system.
Ensures consistency across instructor and student modules.
"""

from typing import Any, Dict, List, Optional, TypedDict
from shared.constants import FieldNames


class QuestionResult(TypedDict):
    """Structure for individual question result in results.json"""

    score: float
    max_score: float
    feedback: str


class ResultsPayload(TypedDict):
    """Structure for the complete results.json file"""

    student_id: str
    timestamp: str
    total_score: float
    max_score: float
    questions: Dict[str, QuestionResult]


class TestResult(TypedDict, total=False):
    """Structure for individual test result (internal use)"""

    test: str
    status: str
    message: str
    score: float
    max_score: float
    student_query: Optional[str]
    expected: Optional[List[List[str]]]
    actual: Optional[List[List[str]]]
    failures: Optional[List[str]]


class TestRunResults(TypedDict, total=False):
    """Structure for complete test run results (internal use)"""

    total_score: float
    max_score: float
    percentage: float
    test_results: List[TestResult]
    error: Optional[str]


class TestData(TypedDict, total=False):
    """Structure for test case definition"""

    query: str
    query_type: str
    score: float
    test_query: Optional[str]
    expected_output: Optional[List[List[str]]]
    validation_query: Optional[str]
    validation_output: Optional[List[List[str]]]
    function_tests: Optional[List[Dict[str, Any]]]
    # Constraint flags
    require_join: Optional[bool]
    forbid_join: Optional[bool]
    require_nested_select: Optional[bool]
    forbid_nested_select: Optional[bool]
    require_group_by: Optional[bool]
    forbid_group_by: Optional[bool]
    require_order_by: Optional[bool]
    forbid_order_by: Optional[bool]
    constraint_violations: Optional[List[str]]


class DBConfig(TypedDict):
    """Database configuration structure"""

    host: str
    port: int
    user: str
    password: str
    database: str


def create_db_config(
    host: str = "localhost",
    port: int = 3306,
    user: str = "root",
    password: str = "",
    database: str = "",
) -> DBConfig:
    """Factory function to create a DBConfig"""
    return DBConfig(
        host=host, port=port, user=user, password=password, database=database
    )


def create_question_result(
    score: float, max_score: float, feedback: str
) -> QuestionResult:
    """Factory function to create a QuestionResult"""
    return QuestionResult(score=score, max_score=max_score, feedback=feedback)


def create_results_payload(
    student_id: str,
    timestamp: str,
    total_score: float,
    max_score: float,
    questions: Dict[str, QuestionResult],
) -> ResultsPayload:
    """Factory function to create a ResultsPayload"""
    return ResultsPayload(
        student_id=student_id,
        timestamp=timestamp,
        total_score=total_score,
        max_score=max_score,
        questions=questions,
    )


def test_result_to_question_result(test_result: TestResult) -> QuestionResult:
    """Convert a TestResult to a QuestionResult for results.json"""
    status = test_result.get(FieldNames.STATUS, "UNKNOWN")
    score = test_result.get(FieldNames.SCORE, 0)
    max_score = test_result.get(FieldNames.MAX_SCORE, 0)
    message = test_result.get(FieldNames.MESSAGE, "")

    if status == FieldNames.STATUS_PASS:
        feedback = FieldNames.FEEDBACK_PASS
    else:
        feedback = message if message else status

    return create_question_result(score, max_score, feedback)


def format_question_for_excel(question_result: QuestionResult) -> str:
    """Format a QuestionResult for Excel display"""
    if question_result[FieldNames.FEEDBACK] == FieldNames.FEEDBACK_PASS:
        return f"{question_result[FieldNames.SCORE]}/{question_result[FieldNames.MAX_SCORE]}"
    else:
        return question_result[FieldNames.FEEDBACK]
