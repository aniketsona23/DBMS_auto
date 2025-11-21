from pathlib import Path

# Set to True to disable encryption and use plain .json files for debugging
DEBUG_MODE = False

EVAL_TESTS_FILENAME = "eval_tests.json" if DEBUG_MODE else "eval_tests.json.enc"
SAMPLE_TESTS_FILENAME = "sample_tests.json" if DEBUG_MODE else "sample_tests.json.enc"

# Note: student_id needs to be formatted in
RESULTS_FILENAME_TEMPLATE = (
    "{student_id}_results.json" if DEBUG_MODE else "{student_id}_results.json.enc"
)

# For creating the student package
PACKAGE_EVAL_TESTS_FILENAME = "eval_tests.json" if DEBUG_MODE else "eval_tests.json.enc"
PACKAGE_SAMPLE_TESTS_FILENAME = (
    "sample_tests.json" if DEBUG_MODE else "sample_tests.json.enc"
)

# Path constants

REPO_PATH = Path(__file__).resolve().parent.parent

STUDENT_DIR = REPO_PATH / "student"
INSTRUCTOR_DIR = REPO_PATH / "instructor"
KEY_PATH = REPO_PATH / "shared" / ".encryption_key"

# Common build and dist directories for both executables
COMMON_BUILD_DIR = REPO_PATH / "build"
COMMON_DIST_DIR = REPO_PATH / "dist"

# Student executable paths
RUN_TESTCASE_PATH = STUDENT_DIR / "run_testcase.py"
RUN_TESTCASE_SPEC = STUDENT_DIR / "run_testcase.spec"
RUN_TESTCASE_EXECUTABLE_PATH = COMMON_DIST_DIR / "run_testcase"

# Instructor executable paths
DECRYPT_SCRIPT_PATH = INSTRUCTOR_DIR / "utils" / "decrypt_and_append.py"
LIST_SCORES_SPEC = REPO_PATH / "list_scores.spec"
LIST_SCORES_EXECUTABLE_PATH = COMMON_DIST_DIR / "list_scores"

# Build script path
BUILD_SCRIPT_PATH = INSTRUCTOR_DIR / "scripts" / "build_executable.sh"

# Instructor directories
INSTRUCTOR_PUBLIC_DIR = INSTRUCTOR_DIR / "public"
INSTRUCTOR_DIST_DIR = COMMON_DIST_DIR  # Use common dist directory

# Test files
TESTS_JSON_PATH = REPO_PATH / "tests.json"
SAMPLE_TESTS_JSON_PATH = REPO_PATH / "sample_tests.json"

# Server configuration
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000


# Field name constants for consistency
class FieldNames:
    """Standardized field names used across the system"""

    # Results payload fields
    STUDENT_ID = "student_id"
    TIMESTAMP = "timestamp"
    TOTAL_SCORE = "total_score"
    MAX_SCORE = "max_score"
    QUESTIONS = "questions"
    TEST_RESULTS = "test_results"

    # Question result fields
    SCORE = "score"
    FEEDBACK = "feedback"

    # Test result fields
    TEST = "test"
    STATUS = "status"
    MESSAGE = "message"
    STUDENT_QUERY = "student_query"
    EXPECTED = "expected"
    ACTUAL = "actual"
    FAILURES = "failures"

    # Test data fields
    QUERY = "query"
    QUERY_TYPE = "query_type"
    TEST_QUERY = "test_query"
    EXPECTED_OUTPUT = "expected_output"
    VALIDATION_QUERY = "validation_query"
    VALIDATION_OUTPUT = "validation_output"
    FUNCTION_TESTS = "function_tests"

    # Constraint fields
    REQUIRE_JOIN = "require_join"
    FORBID_JOIN = "forbid_join"
    REQUIRE_NESTED_SELECT = "require_nested_select"
    FORBID_NESTED_SELECT = "forbid_nested_select"
    REQUIRE_GROUP_BY = "require_group_by"
    FORBID_GROUP_BY = "forbid_group_by"
    REQUIRE_ORDER_BY = "require_order_by"
    FORBID_ORDER_BY = "forbid_order_by"
    CONSTRAINT_VIOLATIONS = "constraint_violations"

    # Database config fields
    HOST = "host"
    PORT = "port"
    USER = "user"
    PASSWORD = "password"
    DATABASE = "database"
    DB_CONFIG = "_db_config"

    # Status values
    STATUS_PASS = "PASS"
    STATUS_FAIL = "FAIL"
    STATUS_ERROR = "ERROR"
    STATUS_WARNING = "WARNING"
    STATUS_MISSING = "MISSING"

    # Feedback values
    FEEDBACK_PASS = "Pass"

    # API Response fields
    SAMPLE_TESTS = "sample_tests"
    EVAL_TESTS = "eval_tests"
    BUILD_STATUS = "build_status"
    LIST_SCORES_STATUS = "list_scores_status"
    SUCCESS = "success"
    EXECUTABLE_READY = "executable_ready"
    EXECUTABLE_PATH = "executable_path"


# Query type constants
class QueryType:
    """Query type values"""

    SELECT = "select"
    VIEW = "view"
    DDL = "ddl"
    DDL_DML = "ddl_dml"
    TABLE = "table"
    FUNCTION = "function"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    DML = "dml"
    UNKNOWN = "unknown"


# Error messages
class ErrorMessages:
    """Standard error messages"""

    DB_CONFIG_NOT_FOUND = "Error: Database configuration not found in test file"
    DB_FIELD_MISSING = "Error: Missing required database field: {field}"
    SOLUTION_NOT_FOUND = "Error: Solution file not found: {path}"
    TESTS_NOT_FOUND = "Error: Tests file not found: {path}"
    DB_CONNECTION_FAILED = "Failed to connect to database or run tests: {error}"
    SOLUTION_READ_FAILED = "Failed to read solution file: {error}"
    SOLUTION_PARSE_FAILED = "Failed to parse solution SQL: {error}"
    TESTS_LOAD_FAILED = "Error loading tests: {error}"


# Constraint flags list for iteration
CONSTRAINT_FLAGS = [
    FieldNames.REQUIRE_JOIN,
    FieldNames.FORBID_JOIN,
    FieldNames.REQUIRE_NESTED_SELECT,
    FieldNames.FORBID_NESTED_SELECT,
    FieldNames.REQUIRE_GROUP_BY,
    FieldNames.FORBID_GROUP_BY,
    FieldNames.REQUIRE_ORDER_BY,
    FieldNames.FORBID_ORDER_BY,
]


# Required database configuration fields
REQUIRED_DB_FIELDS = [
    FieldNames.HOST,
    FieldNames.PORT,
    FieldNames.USER,
    FieldNames.PASSWORD,
    FieldNames.DATABASE,
]
