#!/usr/bin/env python3
"""
routes.py

Central routing for API endpoints. Keeps HTTP routing logic out of the server entrypoint.
"""
from instructor.api.handlers import (
    handle_parse,
    handle_reset_db,
    handle_create_tests,
    handle_test_connection,
    handle_create_package,
    handle_static_file,
    handle_download_list_scores,
)


def route_request(method: str, path: str, body: bytes, content_type: str):
    """Route incoming HTTP requests (GET/POST) to the appropriate handler.

    Returns a tuple: (status_code, response_body, content_type)
    """
    method = (method or "").upper()

    if method == "GET":
        # Download list_scores executable
        if path.startswith("/download-list-scores"):
            return handle_download_list_scores()
        # Static file serving is implemented in handlers.handle_static_file
        return handle_static_file(path)

    if method == "POST":
        if path.startswith("/parse"):
            return handle_parse(body, content_type)
        elif path.startswith("/test-connection"):
            return handle_test_connection(body)
        elif path.startswith("/reset-db"):
            return handle_reset_db(body, content_type)
        elif path.startswith("/create-tests"):
            return handle_create_tests(body)
        elif path.startswith("/create-package"):
            return handle_create_package(body, content_type)
        else:
            return 404, "Not found", "text/plain"

    return 405, "Method not allowed", "text/plain"
