import os
import sys
import json
import re
import zipfile
from pathlib import Path
from openpyxl import Workbook, load_workbook
from cryptography.fernet import Fernet


def get_key():
    """Get encryption key from environment or use default."""
    key = os.environ.get("FERNET_KEY")
    if not key:
        key = b"nVPZZCjg6EFcWrch2Ivk13WWXNv7uWZGU5C5Vc2ADrw="
    return key.encode() if isinstance(key, str) else key


def extract_student_id(filename: str) -> str:
    """
    Extract student ID from filename pattern: YYYY[A-Z][A-Z or 0-9][A-Z][A-Z or 0-9][0-9][0-9][0-9][0-9]G
    Example: 2024AB12C3456G -> 2024AB12C3456G
    """
    # Pattern: 4 digits + [A-Z] + [A-Z0-9] + [A-Z] + [A-Z0-9] + 4 digits + G
    pattern = r"(\d{4}[A-Z][A-Z0-9][A-Z][A-Z0-9]\d{4}G)"
    match = re.search(pattern, filename, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return ""


def find_results_json(inner_zip_path: Path, key: bytes) -> dict:
    """Find and decrypt results.json from inner ZIP file."""
    with zipfile.ZipFile(inner_zip_path, "r") as inner_zip:
        for file_info in inner_zip.namelist():
            if file_info.endswith(".json.enc") or file_info.endswith(
                "results.json.enc"
            ):
                encrypted_data = inner_zip.read(file_info)
                fernet = Fernet(key)
                try:
                    decrypted_data = fernet.decrypt(encrypted_data)
                    return json.loads(decrypted_data.decode("utf-8"))
                except Exception as e:
                    print(f"[WARNING] Failed to decrypt {file_info}: {e}")
    return {}


def process_zip_file(zip_path: Path, key: bytes, excel_path: str) -> bool:
    """Process a single outer ZIP file and extract results."""
    filename = zip_path.name
    student_id_from_zip = extract_student_id(filename)

    if not student_id_from_zip:
        print(f"[WARNING] Could not extract student ID from: {filename}")
        return False

    print(f"[INFO] Processing {filename} -> Student ID: {student_id_from_zip}")

    try:
        with zipfile.ZipFile(zip_path, "r") as outer_zip:
            # Look for inner ZIP file
            inner_zip_files = [f for f in outer_zip.namelist() if f.endswith(".zip")]

            if not inner_zip_files:
                print(f"[WARNING] No inner ZIP found in {filename}")
                return False

            # Extract first inner ZIP to temp location
            inner_zip_name = inner_zip_files[0]
            inner_zip_data = outer_zip.read(inner_zip_name)
            temp_inner = Path(f"temp_{student_id_from_zip}.zip")
            temp_inner.write_bytes(inner_zip_data)

            try:
                # Find and decrypt results.json
                results = find_results_json(temp_inner, key)

                if not results:
                    print(f"[WARNING] No results found in {filename}")
                    return False

                # Extract data from results
                uploaded_id = results.get("student_id", student_id_from_zip)
                timestamp = results.get("timestamp", "")
                total_score = results.get("total_score", 0)
                max_score = results.get("max_score", 0)
                test_results = results.get("test_results", [])

                # Build question feedback dictionary
                questions = {}
                for test in test_results:
                    test_key = test.get("test", "")
                    status = test.get("status", "")
                    message = test.get("message", "")
                    score = test.get("score", 0)
                    max_score_q = test.get("max_score", 0)

                    if status == "PASS":
                        # For passed questions, show the score
                        questions[test_key] = f"{score}/{max_score_q}"
                    else:
                        # For failed questions, show the feedback message
                        questions[test_key] = message if message else status

                # Append to Excel
                append_to_excel(
                    excel_path=excel_path,
                    student_id_zip=student_id_from_zip,
                    uploaded_id=uploaded_id,
                    timestamp=timestamp,
                    total_score=total_score,
                    questions=questions,
                )

                print(
                    f"[SUCCESS] Processed {student_id_from_zip}: {total_score}/{max_score} at {timestamp}"
                )
                return True

            finally:
                # Cleanup temp file
                if temp_inner.exists():
                    temp_inner.unlink()

    except Exception as e:
        print(f"[ERROR] Failed to process {filename}: {e}")
        return False


def append_to_excel(
    excel_path: str,
    student_id_zip: str,
    uploaded_id: str,
    timestamp: str,
    total_score: float,
    questions: dict,
):
    """Append results to Excel file."""
    # Prepare headers
    base_cols = ["student_id", "uploaded_id", "timestamp"]

    # Sort question keys
    question_keys = sorted(
        questions.keys(),
        key=lambda k: int(k[1:]) if k.startswith("q") and k[1:].isdigit() else k,
    )

    # For each question, we want just one column: q1, q2, q3, ...
    # Contains score if passed, feedback if failed
    question_cols = [qk for qk in question_keys]

    all_cols = base_cols + question_cols + ["total_score"]

    # Prepare row data
    new_row = [student_id_zip, uploaded_id, timestamp]
    for qk in question_keys:
        new_row.append(questions.get(qk, ""))
    new_row.append(total_score)

    # Load or create workbook
    if os.path.exists(excel_path):
        wb = load_workbook(excel_path)
        ws = wb.active

        # Update headers if needed
        existing = [cell.value for cell in ws[1]]
        for idx, col in enumerate(all_cols):
            if idx >= len(existing) or existing[idx] != col:
                ws.cell(row=1, column=idx + 1).value = col
    else:
        wb = Workbook()
        ws = wb.active
        for idx, col in enumerate(all_cols):
            ws.cell(row=1, column=idx + 1).value = col

    # Append row
    ws.append(new_row)
    wb.save(excel_path)
    print(
        f"[INFO] Appended to {excel_path}: {student_id_zip} -> total_score: {total_score}"
    )


def main():
    """Main function to process all ZIP files in current directory."""
    current_dir = Path.cwd()
    excel_path = "grades.xlsx"

    # Get encryption key
    key = get_key()

    # Find all ZIP files in current directory
    zip_files = list(current_dir.glob("*.zip"))

    if not zip_files:
        print("[INFO] No ZIP files found in current directory")
        return

    print(f"[INFO] Found {len(zip_files)} ZIP file(s) to process")
    print(f"[INFO] Output will be saved to: {excel_path}")
    print("-" * 60)

    success_count = 0
    for zip_path in zip_files:
        if process_zip_file(zip_path, key, excel_path):
            success_count += 1
        print()

    print("-" * 60)
    print(
        f"[SUMMARY] Successfully processed {success_count}/{len(zip_files)} ZIP files"
    )
    print(f"[SUMMARY] Results saved to: {excel_path}")


if __name__ == "__main__":
    main()
