#!/usr/bin/env python3
"""
handler.py

HTTP request handler class. This file centralizes the BaseHTTPRequestHandler
subclass so `run_server.py` only starts the server.
"""

from http.server import BaseHTTPRequestHandler
import sys
from urllib.parse import urlparse

from instructor.api.routes import route_request


class Handler(BaseHTTPRequestHandler):
    """HTTP request handler with routing delegated to `handlers.routes`.

    Class attributes `ENV_VARS` and `DB_CONFIG` are loaded once when the
    class is defined so handlers can access database configuration.
    """

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
        """Handle GET requests - delegate to router for static files."""
        path = urlparse(self.path).path
        code, body, ctype = route_request("GET", path, b"", "")
        self._respond(code, body, ctype)

    def do_POST(self):
        """Handle POST requests - delegate to router for API endpoints."""
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b""
        content_type = self.headers.get("Content-Type", "")

        code, response, ctype = route_request("POST", path, body, content_type)
        self._respond(code, response, ctype)

    def log_message(self, format, *args):
        """Log requests to stderr."""
        sys.stderr.write(
            "%s - - [%s] %s\n"
            % (self.client_address[0], self.log_date_time_string(), format % args)
        )
