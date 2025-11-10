#!/usr/bin/env python3
"""
run_server.py

Main server entry point for the SQL test generation web UI.
Provides endpoints for parsing SQL, resetting database, and creating tests.

This server is for local development only.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import sys
from urllib.parse import urlparse

from config import get_server_config, get_db_config, load_env_file
from handlers.handlers import (
    handle_parse,
    handle_reset_db,
    handle_create_tests,
    handle_static_file,
    handle_test_connection,
    handle_create_package,
)


class Handler(BaseHTTPRequestHandler):
    """HTTP request handler with routing to endpoint handlers."""

    # Load env vars once when class is defined
    ENV_VARS = load_env_file()
    DB_CONFIG = get_db_config(ENV_VARS)

    def _respond(self, code, body, content_type="text/plain"):
        """Send HTTP response with proper headers."""
        if isinstance(body, str):
            body_bytes = body.encode("utf-8")
        elif isinstance(body, bytes):
            body_bytes = body
        else:
            body_bytes = str(body).encode("utf-8")

        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        """Handle GET requests - serve static files."""
        path = urlparse(self.path).path
        code, body, ctype = handle_static_file(path)
        self._respond(code, body, ctype)

    def do_POST(self):
        """Handle POST requests - route to appropriate handler."""
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b""
        content_type = self.headers.get("Content-Type", "")

        # Route to handlers
        if path.startswith("/parse"):
            code, response, ctype = handle_parse(body, content_type)
        elif path.startswith("/test-connection"):
            code, response, ctype = handle_test_connection(body, self.DB_CONFIG)
        elif path.startswith("/reset-db"):
            code, response, ctype = handle_reset_db(body, content_type, self.DB_CONFIG)
        elif path.startswith("/create-tests"):
            code, response, ctype = handle_create_tests(body, self.DB_CONFIG)
        elif path.startswith("/create-package"):
            code, response, ctype = handle_create_package(body, content_type)
        else:
            code, response, ctype = 404, "Not found", "text/plain"

        self._respond(code, response, ctype)

    def log_message(self, format, *args):
        """Log requests to stderr."""
        sys.stderr.write(
            "%s - - [%s] %s\n"
            % (self.client_address[0], self.log_date_time_string(), format % args)
        )


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
