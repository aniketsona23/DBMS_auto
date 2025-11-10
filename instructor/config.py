#!/usr/bin/env python3
"""
config.py

Configuration management for the test generation server.
Handles environment variables and .env file loading.
"""
import os

# Repo layout
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(THIS_DIR)
WEB_DIR = os.path.join(THIS_DIR, "public")



def load_env_file():
    """Load environment variables from .env.local or .env file."""
    env_vars = {}
    for candidate in (
        os.path.join(REPO_ROOT, ".env.local"),
        os.path.join(REPO_ROOT, ".env"),
    ):
        if os.path.exists(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip()
            except Exception:
                pass
    return env_vars


def get_db_config(env_vars=None):
    """Get database configuration from environment or .env file."""
    if env_vars is None:
        env_vars = {}

    return {
        "host": os.environ.get("DB_HOST", env_vars.get("DB_HOST", "127.0.0.1")),
        "port": int(os.environ.get("DB_PORT", env_vars.get("DB_PORT", "3306"))),
        "user": os.environ.get("DB_USER", env_vars.get("DB_USER", "root")),
        "password": os.environ.get("DB_PASS", env_vars.get("DB_PASS", "")),
        "database": os.environ.get("DB_NAME", env_vars.get("DB_NAME", "")),
    }


def get_server_config():
    """Get server host and port configuration."""
    return {
        "host": os.environ.get("HOST", "127.0.0.1"),
        "port": int(os.environ.get("PORT", "8000")),
    }
