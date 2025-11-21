# Makefile for DBMS_SOP Project

.PHONY: help run clean build-student build-list-scores build-all install

# Default target
help:
	@echo "Available commands:"
	@echo "  make run              - Start the instructor web server"
	@echo "  make clean            - Clean all build artifacts and cache"
	@echo "  make build-student    - Build the student executable"
	@echo "  make build-list-scores - Build the list_scores executable"
	@echo "  make build-all        - Build both executables"
	@echo "  make install          - Install Python dependencies"

# Run the instructor server
run:
	. venv/bin/activate && python3 -m instructor.run_server

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	@rm -rf build/ dist/
	@rm -rf student/build/ student/dist/
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type f -name "*.spec" -delete 2>/dev/null || true
	@rm -f temp_*.zip 2>/dev/null || true
	@rm -f run_testcase run_testcase.exe 2>/dev/null || true
	@rm -f list_scores list_scores.exe 2>/dev/null || true
	@echo "✓ Build artifacts cleaned"
	@echo "✓ Python cache cleaned"
	@echo "✓ Temporary files removed"

# Build student executable
build-student:
	@echo "Building student executable..."
	@python -c "from instructor.api.services import build_student_executable; success, msg, path = build_student_executable(); print(msg); exit(0 if success else 1)"

# Build list_scores executable
build-list-scores:
	@echo "Building list_scores executable..."
	@python -c "from instructor.api.services import build_list_scores_executable; success, msg, path = build_list_scores_executable(); print(msg); exit(0 if success else 1)"

# Build all executables
build-all: build-student build-list-scores
	@echo ""
	@echo "All executables built successfully!"

# Install dependencies
install:
	pip install -r requirements.txt
