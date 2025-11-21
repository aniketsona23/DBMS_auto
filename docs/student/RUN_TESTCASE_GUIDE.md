# Quick Student Guide — Running Tests & Submitting

This is a concise guide for students to run the test runner, produce the encrypted results, and create the submission ZIP to upload to QuantaAWS.

Key points (short):

- DO NOT modify any generated files or the `.json.enc` files distributed with the assignment.
- Upload the generated `<student_id>_submission.zip` to QuantaAWS (see your course instructions).

### Commands

- Run sample tests:

```
chmod +x ./run_testcase
./run_testcase
```

- Run eval tests and create final submission ZIP (use your student id):

```
# Replace STUDENT_ID with your ID, e.g. 2021a7ps0001g
./run_testcase --zip STUDENT_ID
```

### What these commands produce

- Graded run (`--zip STUDENT_ID`):
  - Creates an encrypted results file named `<STUDENT_ID>_results.json.enc` in the current directory.
  - Creates a submission ZIP named `<STUDENT_ID>_submission.zip` containing:
    - `solution.sql` (your submitted SQL file)
    - `<STUDENT_ID>_results.json.enc` (the encrypted result payload)

### Important rules — read carefully

- Do NOT edit any of the provided `.json.enc` test files (for example `eval_tests.json.enc` or `sample_tests.json.enc`). These are cryptographically protected and must remain unchanged.
- Do NOT manually modify generated files such as `<STUDENT_ID>_results.json.enc` or `<STUDENT_ID>_submission.zip` after they are created. Any modifications may invalidate the submission.

### Upload

- Upload the file named `<STUDENT_ID>_submission.zip` to QuantaAWS according to your course instructions.

### Troubleshooting

- If the runner prints an error about missing tests like `eval_tests.json.enc` or `sample_tests.json.enc`, ensure you are running from the directory that contains the test files (project root) or copy the tests into your working directory.
- If you see messages about a freshly-generated encryption key at runtime, rebuild was done without bundling the repository key. Contact instructors if you see this during grading runs.

### Contact

- For any issues with submission or the runner, contact your instructor / TA and include the exact command you ran and any error output.

### Good luck!
