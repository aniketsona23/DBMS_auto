#!/usr/bin/env python3
"""
run_server.py

Main server entry point for the SQL test generation web UI.
Provides endpoints for parsing SQL, resetting database, and creating tests.

This server is for local development only.
"""

from http.server import HTTPServer
from shared.constants import SERVER_HOST, SERVER_PORT
from shared.logger import get_logger
from instructor.handler import Handler

logger = get_logger(__name__)


# `Handler` implementation lives in `handlers/handler.py`.


def main():
    """Start the HTTP server."""
    host = SERVER_HOST
    port = SERVER_PORT

    logger.info(f"run_server: listening on http://{host}:{port}/")
    logger.info(
        "  Endpoints: /parse, /test-connection, /reset-db, /create-tests, /create-package"
    )

    # Show binary status

    try:
        server = HTTPServer((host, port), Handler)
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("\nStopping server...")


if __name__ == "__main__":
    main()
