import os
import sys
import tempfile
import unittest
from pathlib import Path

from flask import Flask


REPO_ROOT = Path(__file__).resolve().parent.parent
APP_WEB_SERVER_PATH = REPO_ROOT / "app" / "web_server"

if str(APP_WEB_SERVER_PATH) not in sys.path:
    sys.path.insert(0, str(APP_WEB_SERVER_PATH))


def reset_singletons():
    from data_m.db_manager import DBManager
    from user_m.user_manager import UserManager

    DBManager._instance = None
    UserManager._instance = None


class IsolatedDatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.tools_path = Path(self.temp_dir.name) / "tools"
        os.environ["APP_DB_PATH"] = str(self.db_path)
        os.environ["HORIZONE_LITE_TOOLS_PATH"] = str(self.tools_path)
        reset_singletons()

    def tearDown(self):
        reset_singletons()
        os.environ.pop("APP_DB_PATH", None)
        os.environ.pop("HORIZONE_LITE_TOOLS_PATH", None)
        self.temp_dir.cleanup()


class ApiTestCase(IsolatedDatabaseTestCase):
    def setUp(self):
        super().setUp()

        from api_m import ApiManager
        from config_m import ConfigManager
        from data_m import DBManager
        from model_m import ModelManager
        from user_m import UserManager

        self.app = Flask(__name__)
        self.config_manager = ConfigManager()
        self.db = DBManager()
        self.user_manager = UserManager(
            db_manager=self.db,
            secret_key=self.config_manager.runtime.secret_key,
        )
        self.model_manager = ModelManager(self.config_manager, self.db)
        self.api_manager = ApiManager(
            self.app,
            self.user_manager,
            self.db,
            self.model_manager,
        )
        self.client = self.app.test_client()
        self.token = self.user_manager.login("admin", "admin")
        self.auth_headers = {"Authorization": f"Bearer {self.token}"}
