#!/usr/bin/env python3
"""
db_utils.py

Database utilities for connecting to MySQL and executing queries.
"""
import subprocess
import tempfile
import os

try:
    import pymysql
except Exception:
    pymysql = None


def get_db_connection(db_config):
    """
    Create a PyMySQL database connection.

    Args:
        db_config: Dict with keys: host, port, user, password, database

    Returns:
        pymysql.Connection object

    Raises:
        Exception if pymysql is not available or connection fails
    """
    if pymysql is None:
        raise Exception("PyMySQL not installed")

    return pymysql.connect(
        host=db_config["host"],
        port=db_config["port"],
        user=db_config["user"],
        password=db_config["password"],
        db=db_config["database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.Cursor,
        autocommit=False,
    )


def reset_database_via_cli(sql_text, db_config, repo_root):
    """
    Reset database by running SQL via mysql CLI.

    Args:
        sql_text: SQL script content
        db_config: Dict with database configuration
        repo_root: Path to repository root for temp files

    Returns:
        Tuple of (success: bool, output: str)
    """
    try:
        fd, tmp_sql = tempfile.mkstemp(prefix="reset_db_", suffix=".sql", dir=repo_root)
        with os.fdopen(fd, "wb") as f:
            f.write(sql_text.encode("utf-8"))
    except Exception as e:
        return False, f"Failed to write temp SQL file: {e}"

    mysql_cmd = [
        "mysql",
        "-h",
        str(db_config["host"]),
        "-P",
        str(db_config["port"]),
        "-u",
        db_config["user"],
        "-p",
    ]
    if db_config["database"]:
        mysql_cmd.append(db_config["database"])

    env = os.environ.copy()
    if db_config["password"]:
        env["MYSQL_PWD"] = db_config["password"]

    try:
        with open(tmp_sql, "rb") as sqlfile:
            proc = subprocess.run(
                mysql_cmd,
                stdin=sqlfile,
                capture_output=True,
                text=True,
                env=env,
            )
        out = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
    except FileNotFoundError:
        out = "mysql client not found. Install mysql CLI or set PATH so `mysql` is available."
        code = 1
    except Exception as e:
        out = f"Failed to run mysql: {e}"
        code = 1
    finally:
        try:
            os.remove(tmp_sql)
        except Exception:
            pass

    return code == 0, out


def is_pymysql_available():
    """Check if PyMySQL is available."""
    return pymysql is not None
