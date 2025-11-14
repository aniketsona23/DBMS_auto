#!/bin/bash
# build_executable.sh
# Creates a standalone Linux executable for run_testcase.py with encryption key

echo "Building run_testcase executable..."

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo "PyInstaller not found. Installing..."
    pip install pyinstaller
fi

# Check if running in student directory
if [ ! -f "run_testcase.py" ]; then
    echo "Error: run_testcase.py not found. Run this script from the student directory."
    exit 1
fi

# Check if encryption key is set (allow both old and new comment formats)
if grep -q 'ENCRYPTION_KEY = b""' run_testcase.py; then
    echo "WARNING: ENCRYPTION_KEY is not set in run_testcase.py"
    echo "Please set the encryption key before building."
    exit 1
fi


pyinstaller --onefile \
--name run_testcase \
--clean \
--strip \
--noconfirm \
--add-data "../shared:shared" \
--add-data "config.py:." \
--add-data "test_utils.py:." \
--hidden-import pymysql \
--hidden-import cryptography \
run_testcase.py

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Executable created successfully!"
    echo "Location: dist/run_testcase"
    echo "Size: $(du -h dist/run_testcase | cut -f1)"
    echo ""
    echo "Usage:"
    echo "  ./dist/run_testcase solution.sql"
    echo ""
    echo "To make it executable:"
    echo "  chmod +x dist/run_testcase"
else
    echo "Error: Build failed"
    exit 1
fi
