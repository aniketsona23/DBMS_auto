#!/usr/bin/env python3
"""
run_server.py

Main server entry point for the SQL test generation web UI.
Provides endpoints for parsing SQL, resetting database, and creating tests.

This server is for local development only.
"""
from http.server import HTTPServer
from instructor.config import get_server_config
from instructor.handler import Handler


# `Handler` implementation lives in `handlers/handler.py`.


def main():
    """Start the HTTP server."""
    config = get_server_config()
    host = config["host"]
    port = config["port"]

    print(f"run_server: listening on http://{host}:{port}/")
    print(
        f"  Endpoints: /parse, /test-connection, /reset-db, /create-tests, /create-package"
    )

    # Show binary status

    try:
        server = HTTPServer((host, port), Handler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")


if __name__ == "__main__":
    main()
