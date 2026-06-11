# db_connector.py
import os
import sys
import sqlite3
from pathlib import Path

DB_FILENAME = "flask.db"
DB_PATH_ENV = "APP_DB_PATH"
DATA_DIR_ENV = "HORIZONE_DATA_DIR"
APP_DATA_DIRNAME = "horizone"
APP_DISPLAY_NAME = "HORIZONE"


def _default_db_path():
    return _default_data_dir() / DB_FILENAME


def _default_data_dir():
    configured_dir = os.environ.get(DATA_DIR_ENV)
    if configured_dir:
        return Path(configured_dir).expanduser().resolve()

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DISPLAY_NAME

    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_DISPLAY_NAME
        return Path.home() / "AppData" / "Roaming" / APP_DISPLAY_NAME

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home).expanduser().resolve() / APP_DATA_DIRNAME

    return Path.home() / ".local" / "share" / APP_DATA_DIRNAME

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
