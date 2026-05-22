import os
from pathlib import Path

from tests.test_support import IsolatedDatabaseTestCase

from data_m.utils.db_connector import DBConnector, _default_db_path


class DBConnectorTests(IsolatedDatabaseTestCase):
    def test_uses_app_db_path_when_configured(self):
        connector = DBConnector()

        self.assertEqual(connector.db_path, self.db_path.resolve())

    def test_default_path_is_outside_versioned_source_tree(self):
        os.environ.pop("APP_DB_PATH", None)

        connector = DBConnector()
        default_path = _default_db_path()
        source_tree_root = Path(__file__).resolve().parents[2] / "app" / "web_server"

        self.assertEqual(connector.db_path, default_path)
        self.assertFalse(str(default_path).startswith(str(source_tree_root.resolve())))
        self.assertEqual(default_path.name, "flask.db")
        self.assertEqual(default_path.parent.name, ".horizone-lite")
