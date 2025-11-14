#!/usr/bin/env python3
"""
prepare_student_package.py

Minimal CLI wrapper to prepare the student package by ensuring the encryption
key exists and building the standalone `run_testcase` executable.

This script reuses the service-layer helpers to avoid duplication.

Usage:
    python prepare_student_package.py
"""
import sys
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from instructor.api.services import (
    _get_or_create_key,
    build_student_executable,
)  # noqa: E402


def main() -> int:
    print("=" * 70)
    print("Student Package Preparation Tool")
    print("=" * 70)
    print()

    # Step 1: Ensure encryption key exists (creates if missing)
    print("Step 1: Ensuring encryption key...")
    try:
        key = _get_or_create_key()
        print(f"✓ Encryption key ready ({len(key)} bytes)")
    except Exception as e:
        print(f"Error: Failed to create/load encryption key: {e}")
        return 1
    print()

    # Step 2: Build standalone executable using shared service logic
    print("Step 2: Building standalone executable (this may take a few minutes)...")
    ok, message, exe_path = build_student_executable()
    print(message)
    if not ok or not exe_path:
        return 1

    size_mb = Path(exe_path).stat().st_size / (1024 * 1024)
    print(f"✓ Executable created: {exe_path}")
    print(f"  Size: {size_mb:.2f} MB")
    print()

    print("=" * 70)
    print("✓ Student package prepared successfully!")
    print("=" * 70)
    print()
    print("Next steps:")
    print(f"1. The executable is ready at: {exe_path}")
    print(
        "2. Include this executable in the student package ZIP (services.create_student_package will embed it if present)"
    )
    print()
    print("Students can run:")
    print("  chmod +x run_testcase")
    print("  ./run_testcase solution.sql")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
