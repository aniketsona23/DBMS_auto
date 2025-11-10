# Automatic SQL Lab Generation and Grading System

## Project Overview

This system enables instructors to automatically generate and package SQL lab assignments as easy-to-run student ZIPs, and provides robust, constraint-based auto-grading. It features:

- Interactive web UI for building lab/test packages with constraints.
- Secure packaging of an executable grader, encrypted tests, starter files, and questions PDF into a single ZIP for students.
- Fully offline, platform-agnostic test execution for students (no solution/test file visibility; only results revealed).
- Support for SQL style/structure constraints (require/forbid JOIN, GROUP BY, ORDER BY, nested SELECT, etc).

---

## Folder/Component Guide

### `instructor/` — Lab Package Creation & Instructor Tools

- **Web UI** for lab generation. Start the server and open the UI in your browser.
- **Creates:**
  - `run_testcase` executable (platform dependent, built with PyInstaller)
  - Encrypted evaluation test cases (`eval_tests.json.enc`)
  - Plain practice tests (`sample_tests.json`)
  - Starter `solution.sql`
  - `.env.local` with DB credentials
  - `questions.pdf` (uploaded via the UI, optional)
  - All files zipped for easy student download
- **Dependencies:** Python 3, PyMySQL, cryptography, PyInstaller (for build)

### `student/` — Student-side Test Runner

- **`run_testcase.py`**: Main test runner, converted to executable for easy use.
- **Workflow:** Students extract the zip, fill in `solution.sql`, and run the provided executable.
- **Artifacts inside ZIP:**
  - `sample_tests.json` (practice tests, unencrypted)
  - `eval_tests.json.enc` (evaluation tests, encrypted)
- **Produces:** A secure, encrypted `report.json.enc` with their scores, plus a `submission.zip` for upload.

---

## How To Run/Use

### Instructor: Creating a Lab Package

1. **Install dependencies**
   ```sh
   pip install -r instructor/requirements.txt  # install PyMySQL, cryptography, flask, etc.
   ```
2. **Start the instructor server:**
   ```sh
   cd instructor
   python run_server.py
   # Go to http://localhost:8000 in your browser
   ```
3. **Build your lab package:**
   - Enter DB credentials, upload optional `questions.pdf`, and write or paste your SQL queries.
   - Use constraint checkboxes for each query.
   - Click 'Parse', then 'Create Tests'.
   - Download the ZIP student package.

### Student: Attempting the Lab & Submitting

1. **Extract the provided ZIP** anywhere (all files must remain together).
2. **Edit `solution.sql`** with your answers to each query.
3. **(If needed) Edit `.env.local`** with your provided DB credentials.

- Practice DB variables: `SAMPLE_DB_HOST`, `SAMPLE_DB_PORT`, `SAMPLE_DB_USER`, `SAMPLE_DB_PASS`, `SAMPLE_DB_NAME`
- Evaluation DB variables: `EVAL_DB_HOST`, `EVAL_DB_PORT`, `EVAL_DB_USER`, `EVAL_DB_PASS`, `EVAL_DB_NAME`
- Legacy fallback: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME` (used only if the prefixed ones are missing)

4. **Run the test runner:**
   - On Windows:
     `sh
.\run_testcase.exe
    # or
    python run_testcase.py
    `
   - On Linux/macOS:
     `sh
./run_testcase
    # or
    python3 run_testcase.py
    `
5. **Practice vs Evaluation**

- By default (no flags), the runner loads `sample_tests.json` and connects to the SAMPLE\_\* database. No report is saved.
- For the graded run, use `--zip` after the allowed time: this loads `eval_tests.json.enc`, connects to the EVAL\_\* database, and generates an encrypted `results.json.enc` plus `submission.zip`.

6. **When using `--zip`:** You must pass a valid `--student-id` (e.g., `2022b3a70031g`). The runner will create `results.json.enc` and `submission.zip` (with your `solution.sql` and encrypted results).

### Submission Results

- Your instructor can use the decrypt script (`decrypt_and_append.py`) to extract and record all student grades automatically.

---

## Feature Notes

- **Constraints Supported:** require/forbid JOIN, GROUP BY, ORDER BY, nested SELECT (subquery).
- **Questions PDF:** Bundled into zip for complete take-home lab packages.
- **Fully Encrypted:** No access to solution or test cases for students.
- **Automatic/Scripted Build Process:** Uses PyInstaller for packing the test runner.

---

## Troubleshooting

- Ensure correct DB credentials in `.env.local`.
- You must have Python and required libraries installed for instructor tools (students only need the zip/exe and Python if not using the exe).
- If the executable doesn't run, try `python run_testcase.py` directly, or check for missing libraries.
- For constraint errors: follow output remarks and adjust your SQL accordingly!

---

## Advanced

- See `instructor/core/decrypt_and_append.py` for instructor-side bulk grade extraction and Excel integration.
- See `instructor/student/config.py` for custom configuration tweaks.

---

**For further help, see the inline comments in each script or contact the course/lab instructor.**
