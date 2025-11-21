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
from shared.logger import get_logger
from shared.constants import KEY_PATH
from shared.encryption import get_or_create_key
from instructor.api.services import (
    build_student_executable,
)  # noqa: E402

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


logger = get_logger(__name__)


def main() -> int:
    logger.info("=" * 70)
    logger.info("Student Package Preparation Tool")
    logger.info("=" * 70)
    logger.info("")

    # Step 1: Ensure encryption key exists (creates if missing)
    logger.info("Step 1: Ensuring encryption key...")
    try:
        key = get_or_create_key(KEY_PATH)
        logger.info(f"✓ Encryption key ready ({len(key)} bytes)")
    except Exception as e:
        logger.error(f"Error: Failed to create/load encryption key: {e}")
        return 1
    logger.info("")

    # Step 2: Build standalone executable using shared service logic
    logger.info(
        "Step 2: Building standalone executable (this may take a few minutes)..."
    )
    ok, message, exe_path = build_student_executable()
    logger.info(message)
    if not ok or not exe_path:
        return 1

    size_mb = Path(exe_path).stat().st_size / (1024 * 1024)
    logger.info(f"✓ Executable created: {exe_path}")
    logger.info(f"  Size: {size_mb:.2f} MB")
    logger.info("")

    logger.info("=" * 70)
    logger.info("✓ Student package prepared successfully!")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Next steps:")
    logger.info(f"1. The executable is ready at: {exe_path}")
    logger.info(
        "2. Include this executable in the student package ZIP (services.create_student_package will embed it if present)"
    )
    logger.info("")
    logger.info("Students can run:")
    logger.info("  chmod +x run_testcase")
    logger.info("  ./run_testcase solution.sql")
    logger.info("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
