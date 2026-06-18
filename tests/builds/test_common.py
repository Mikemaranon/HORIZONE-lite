import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDS_PATH = REPO_ROOT / "deploy" / "builds"

if str(BUILDS_PATH) not in sys.path:
    sys.path.insert(0, str(BUILDS_PATH))

import common  # noqa: E402


class DesktopBuildCommonTestCase(unittest.TestCase):
    def make_stage_root(self, temp_dir):
        stage_root = Path(temp_dir) / "stage"
        web_server_root = stage_root / "app" / "web_server"
        web_server_root.mkdir(parents=True)
        (web_server_root / "server.py").write_text("", encoding="utf-8")
        (stage_root / "requirements").mkdir()
        (stage_root / "backend_entry.py").write_text("", encoding="utf-8")
        return stage_root

    def test_macos_backend_freeze_collects_mlx_packages(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            stage_root = self.make_stage_root(temp_dir)
            build_root = Path(temp_dir) / "build"

            command = common.pyinstaller_backend_command(stage_root, build_root, "macos")

        self.assertIn("--collect-all", command)
        self.assertIn("mlx_lm", command)
        self.assertIn("mlx", command)

    def test_non_macos_backend_freeze_does_not_collect_mlx_packages(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            stage_root = self.make_stage_root(temp_dir)
            build_root = Path(temp_dir) / "build"

            command = common.pyinstaller_backend_command(stage_root, build_root, "linux")

        self.assertNotIn("mlx_lm", command)
        self.assertNotIn("mlx", command)

    def test_macos_mlx_preflight_reports_missing_runtime(self):
        with patch.object(common, "has_python_module", return_value=False):
            with self.assertRaises(SystemExit) as context:
                common.ensure_macos_mlx_dependencies()

        message = str(context.exception)
        self.assertIn("requirements/requirements-mac.txt", message)
        self.assertIn("mlx-lm", message)

    def test_macos_llama_cpp_gpu_offload_preflight_reports_missing_acceleration(self):
        with patch.object(common, "has_llama_cpp_gpu_offload", return_value=False):
            with self.assertRaises(SystemExit) as context:
                common.ensure_macos_llama_cpp_gpu_offload()

        message = str(context.exception)
        self.assertIn("Metal GPU offload", message)
        self.assertIn("llama-cpp-python", message)

    def test_macos_llama_cpp_gpu_offload_preflight_accepts_accelerated_runtime(self):
        with patch.object(common, "has_llama_cpp_gpu_offload", return_value=True):
            common.ensure_macos_llama_cpp_gpu_offload()

    def test_macos_runtime_bundle_requires_native_llama_server(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "runtime"
            build_root = Path(temp_dir) / "build"
            with patch.object(common, "RUNTIME_DIST_ROOT", runtime_root):
                with patch.object(common, "resolve_native_llama_server_binary", return_value=None):
                    with patch.object(common, "has_llama_cpp_python_server", return_value=True):
                        with patch.object(common.sys, "platform", "darwin"):
                            with self.assertRaises(SystemExit) as context:
                                common.prepare_runtime_bundle(build_root)

        message = str(context.exception)
        self.assertIn("native llama.cpp llama-server", message)
        self.assertIn("Metal Tensor API", message)


if __name__ == "__main__":
    unittest.main()
