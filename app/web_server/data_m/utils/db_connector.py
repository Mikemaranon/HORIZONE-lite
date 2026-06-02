# db_connector.py
import os
import sqlite3
from pathlib import Path

DB_FILENAME = "flask.db"
DB_PATH_ENV = "APP_DB_PATH"
RUNTIME_DIRNAME = ".horizone-lite"


def _default_db_path():
    project_root = Path(__file__).resolve().parents[4]
    return project_root / RUNTIME_DIRNAME / DB_FILENAME

class DBConnector:
    def __init__(self, db_path=None):
        configured_path = db_path or os.environ.get(DB_PATH_ENV)
        if configured_path:
            self.db_path = Path(configured_path).expanduser().resolve()
        else:
            self.db_path = _default_db_path()

        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self):
        # Establish and return a new database connection
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def close(self, conn):
        if conn:
            conn.close()
