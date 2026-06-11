import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests.test_support import APP_WEB_SERVER_PATH


class FakeRuntimeManager:
    def __init__(self, *, config_manager, db_manager):
        self.config_manager = config_manager
        self.db_manager = db_manager
        self.status = "stopped"
        self.error_message = ""

    def start_if_available(self):
        raise RuntimeError("llama.cpp port is occupied")

    def stop(self):
        self.status = "stopped"


class ServerRuntimeStartupTests(unittest.TestCase):
    def test_runtime_startup_failure_is_recorded_without_raising(self):
        import server

        instance = object.__new__(server.Server)
        instance.config_manager = SimpleNamespace(runtime=SimpleNamespace())
        instance.db_manager = object()

        with patch.object(server, "LlamaCppRuntimeManager", FakeRuntimeManager):
            runtime_manager = instance.init_runtime_manager()

        self.assertEqual(runtime_manager.status, "error")
        self.assertIn("llama.cpp port is occupied", runtime_manager.error_message)


if __name__ == "__main__":
    unittest.main()
