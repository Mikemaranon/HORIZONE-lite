import importlib.util
import sys
from pathlib import Path
from shutil import which


class RuntimePaths:
    def __init__(self, runtime_config):
        self.runtime_config = runtime_config

    def resolve_llama_server_binary(self):
        configured = str(self.runtime_config.llama_cpp_binary or "").strip()
        if configured:
            return configured

        return which("llama-server") or ""

    def resolve_llama_server_launch_command(self):
        binary_path = self.resolve_llama_server_binary()
        if binary_path:
            return [binary_path]

        if self._has_llama_cpp_python_server():
            return [sys.executable, "-m", "llama_cpp.server"]

        return []

    def resolve_models_dir(self):
        return Path(self.runtime_config.runtime_models_dir).expanduser()

    def _has_llama_cpp_python_server(self):
        try:
            return importlib.util.find_spec("llama_cpp.server") is not None
        except ModuleNotFoundError:
            return False
