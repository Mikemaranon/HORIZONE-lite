import os
from pathlib import Path

from tests.test_support import IsolatedDatabaseTestCase

from data_m.utils.db_connector import DBConnector, _default_db_path


class DBConnectorTests(IsolatedDatabaseTestCase):
    def test_uses_app_db_path_when_configured(self):
        connector = DBConnector()

        self.assertEqual(connector.db_path, self.db_path.resolve())

    def test_accepts_explicit_db_path(self):
        explicit_path = self.db_path.parent / "explicit.db"

        connector = DBConnector(db_path=explicit_path)

        self.assertEqual(connector.db_path, explicit_path.resolve())

    def test_applies_sqlite_connection_pragmas(self):
        connector = DBConnector()
        connection = connector.connect()
        try:
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
            busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
        finally:
            connector.close(connection)

        self.assertEqual(foreign_keys, 1)
        self.assertEqual(busy_timeout, 5000)
        self.assertEqual(journal_mode.lower(), "wal")
        self.assertEqual(synchronous, 1)

    def test_default_path_is_outside_versioned_source_tree(self):
        os.environ.pop("APP_DB_PATH", None)

        connector = DBConnector()
        default_path = _default_db_path()
        source_tree_root = Path(__file__).resolve().parents[2] / "app" / "web_server"

        self.assertEqual(connector.db_path, default_path)
        self.assertFalse(str(default_path).startswith(str(source_tree_root.resolve())))
        self.assertEqual(default_path.name, "flask.db")
        self.assertEqual(default_path.parent.name, ".horizone-lite")
