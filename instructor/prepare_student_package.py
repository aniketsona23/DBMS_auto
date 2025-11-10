#!/usr/bin/env python3
"""
prepare_student_package.py

Prepares the student package with encryption key embedded in run_testcase executable.
Run this script from the instructor directory after creating tests.

Usage:
    python prepare_student_package.py
"""
import os
import sys
import subprocess
import shutil

# Add parent directory to path to import from instructor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_encryption_key():
    """Get the encryption key from .encryption_key file."""
    key_path = os.path.join(os.path.dirname(__file__), ".encryption_key")
    if not os.path.exists(key_path):
        print(f"Error: Encryption key file not found: {key_path}")
        print("Please create tests first to generate the encryption key.")
        sys.exit(1)

    with open(key_path, "rb") as f:
        return f.read()


def update_run_testcase_key(student_dir, key):
    """Update the ENCRYPTION_KEY in student's run_testcase.py"""
    run_testcase_path = os.path.join(student_dir, "run_testcase.py")

    if not os.path.exists(run_testcase_path):
        print(f"Error: {run_testcase_path} not found")
        sys.exit(1)

    with open(run_testcase_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace the empty key with actual key
    updated_content = content.replace(
        "ENCRYPTION_KEY = b''  # Instructor: Replace with actual key before creating executable",
        f"ENCRYPTION_KEY = {repr(key)}  # Set by prepare_student_package.py",
    )

    with open(run_testcase_path, "w", encoding="utf-8") as f:
        f.write(updated_content)

    print(f"✓ Updated encryption key in {run_testcase_path}")


def build_executable(student_dir):
    """Build the executable using build_executable.sh"""
    build_script = os.path.join(student_dir, "build_executable.sh")

    if not os.path.exists(build_script):
        print(f"Error: Build script not found: {build_script}")
        sys.exit(1)

    print("\nBuilding executable...")
    print("This may take a few minutes...\n")

    # Make script executable
    os.chmod(build_script, 0o755)

    # Run build script
    result = subprocess.run(
        ["bash", build_script], cwd=student_dir, capture_output=True, text=True
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    if result.returncode != 0:
        print("Error: Build failed")
        sys.exit(1)

    executable_path = os.path.join(student_dir, "dist", "run_testcase")
    if not os.path.exists(executable_path):
        print("Error: Executable not created")
        sys.exit(1)

    return executable_path


def main():
    """Main entry point."""
    print("=" * 70)
    print("Student Package Preparation Tool")
    print("=" * 70)
    print()

    # Get paths - student folder is inside instructor directory
    script_dir = os.path.dirname(os.path.abspath(__file__))  # instructor/
    student_dir = os.path.join(script_dir, "student")  # instructor/student/

    if not os.path.exists(student_dir):
        print(f"Error: Student directory not found: {student_dir}")
        sys.exit(1)

    print(f"Instructor directory: {script_dir}")
    print(f"Student directory: {student_dir}")
    print()

    # Step 1: Get encryption key
    print("Step 1: Loading encryption key...")
    key = get_encryption_key()
    print(f"✓ Encryption key loaded ({len(key)} bytes)")
    print()

    # Step 2: Update run_testcase.py with key
    print("Step 2: Updating run_testcase.py with encryption key...")
    update_run_testcase_key(student_dir, key)
    print()

    # Step 3: Build executable
    print("Step 3: Building standalone executable...")
    executable_path = build_executable(student_dir)
    print(f"✓ Executable created: {executable_path}")

    # Get file size
    size_mb = os.path.getsize(executable_path) / (1024 * 1024)
    print(f"  Size: {size_mb:.2f} MB")
    print()

    # Step 4: Instructions
    print("=" * 70)
    print("✓ Student package prepared successfully!")
    print("=" * 70)
    print()
    print("Next steps:")
    print(f"1. The executable is ready at: {executable_path}")
    print("2. Include this executable in the student package ZIP")
    print("3. Update the package creation to include this file")
    print()
    print("The executable includes:")
    print("  - Encrypted tests decryption")
    print("  - SQL parser")
    print("  - Test runner")
    print("  - All dependencies")
    print()
    print("Students can run:")
    print("  chmod +x run_testcase")
    print("  ./run_testcase solution.sql")
    print()


if __name__ == "__main__":
    main()
