"""
logger.py

Centralized logging configuration for the DBMS test runner system.
Provides consistent logging across all modules.
"""

import logging
import sys
from pathlib import Path
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color support for console output"""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        if sys.stderr.isatty():  # Only use colors if output is to terminal
            log_color = self.COLORS.get(record.levelname, self.RESET)
            record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    use_colors: bool = True,
) -> logging.Logger:
    """
    Set up a logger with console and optional file output.

    Args:
        name: Logger name (typically __name__)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        use_colors: Whether to use colored output for console

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    if use_colors:
        console_format = ColoredFormatter("%(levelname)s - %(message)s")
    else:
        console_format = logging.Formatter("%(levelname)s - %(message)s")

    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_format = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with default configuration.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return setup_logger(name)


# Default application logger
app_logger = get_logger("dbms_test_runner")
