# Web UI Guide for Instructors

This guide provides step-by-step instructions for using the web-based interface to create and distribute test packages to students.

---

## Prerequisites

Before you begin, ensure you have the following:

- **MySQL Databases**: Create both sample and test databases in MySQL (tables and data can be added later via SQL scripts)
- **Solution File**: `solution.sql` containing instructor's solution queries for each question
- **Question Document**: `questions.pdf` with problem statements for students
- **Database Credentials**: MySQL username (e.g., `root`, `csf212`), password, and database names
- **SQL Scripts**: Database initialization scripts for both sample and test databases

---

## Installation

### 1. Set Up Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

![Installation Steps](installation.png)

---

## Usage

### 1. Start the Server

Run the following command to start the web server:

```bash
make run
```

This will start the web server. Open the displayed link (e.g., `http://127.0.0.1:8000`) in your browser.

![Usage Step 1](./server_start.png)

### 2. Open the Webpage

Navigate to the server URL in your browser:

```
http://localhost:8000
```

![Usage Step 2](ui.png)

### 3. Configure Database Credentials

1. Enter the **Sample Database** credentials (for student practice)
2. Enter the **Evaluation Database** credentials (for grading)
3. Click **Test Connection** for both databases to verify connectivity

![Usage Step 3](connect_db.png)

### 4. Upload Files and Reset Databases

Upload the following files:

- **solution.sql** - Contains the instructor's solution queries
- **questions.pdf** - Problem statement for students
- **sample_database.sql** - SQL script for sample database
- **test_database.sql** - SQL script for evaluation database

Then reset the databases:

- Click **Reset Sample DB** to initialize the sample database
- Click **Reset Test DB** to initialize the evaluation database

![Usage Step 4](upload_documents.png)

### 5. Parse Queries

Click **Parse Queries** to extract individual queries from `solution.sql`. Each query will appear in a separate box for configuration.

![Usage Step 5](parser_queries.png)

### 6. Add Constraints

For each query, you can add constraints such as:

- **Require Join** / **Forbid Join**
- **Require Nested Select** / **Forbid Nested Select**
- **Require Group By** / **Forbid Group By**
- **Require Order By** / **Forbid Order By**

![Usage Step 6](constraints.png)

### 7. Set Scores

Assign point values to each query based on difficulty.

![Usage Step 7](change_score.png)

### 8. Create Tests

Click **Create Tests** to generate:

- Sample tests (for student practice)
- Evaluation tests (for grading)
- Executables (`run_testcase` and `list_scores`)

Monitor the logs for build progress and completion status.

![Usage Step 8](create_tests.png)

### 9. Download Student Package

Once test creation is complete:

1. Click **Download Student Package** to get `student_package.zip`
2. Check logs to confirm all files are included
3. Share `student_package.zip` with students

**Package Contents:**

- `eval_tests.json.enc` (encrypted evaluation tests with database credentials)
- `sample_tests.json.enc` (practice tests with database credentials)
- `solution.sql` (template file for students)
- `run_testcase` (executable for running tests)
- `questions.pdf` (if uploaded)

![Usage Step 9](downloaded_packages.png)

---

## Notes

- Ensure both databases are accessible and credentials are correct before creating tests
- The `list_scores` executable is for instructors to decrypt and compile student submissions
- Students will use `run_testcase` to test their solutions locally against sample and evaluation tests
