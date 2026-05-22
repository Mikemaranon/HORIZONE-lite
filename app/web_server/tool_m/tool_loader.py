import importlib.util
import os
import shutil
from pathlib import Path

from werkzeug.utils import secure_filename

from .tool_contract import validate_tool_module


class ToolLoader:
    BUILTIN_FILENAMES = {
        "current_date.py",
        "web_search.py",
    }

    def __init__(self, tools_directory=None):
        self.package_tools_directory = Path(__file__).resolve().parent / "tools"
        configured_directory = (
            tools_directory
            or os.environ.get("HORIZONE_LITE_TOOLS_PATH")
            or self.package_tools_directory
        )
        self.tools_directory = Path(configured_directory)
        self.tools_directory.mkdir(parents=True, exist_ok=True)
        self._seed_builtin_tools()

    def get_catalog_signature(self):
        signature = []
        for tool_path in self.list_tool_files():
            stat = tool_path.stat()
            signature.append((tool_path.name, stat.st_mtime_ns, stat.st_size))
        return tuple(signature)

    def list_tool_files(self):
        return sorted(
            (
                path
                for path in self.tools_directory.glob("*.py")
                if path.name != "__init__.py"
            ),
            key=lambda path: path.name.lower(),
        )

    def load_tools(self):
        tools = []
        for tool_path in self.list_tool_files():
            tools.append(self.load_tool_from_path(tool_path))
        return tools

    def load_tool_from_path(self, tool_path):
        tool_path = Path(tool_path)
        module = self._load_module(tool_path)
        return validate_tool_module(
            module,
            tool_path,
            is_builtin=tool_path.name in self.BUILTIN_FILENAMES,
        )

    def save_source_file(self, filename, source_text):
        normalized_filename = secure_filename(filename or "")
        if not normalized_filename or not normalized_filename.endswith(".py"):
            raise ValueError("Tool files must use the .py extension.")

        destination = self.tools_directory / normalized_filename
        if destination.exists():
            raise ValueError("A tool with that filename already exists.")

        destination.write_text(source_text, encoding="utf-8")
        return destination

    def save_uploaded_file(self, uploaded_file):
        if not uploaded_file:
            raise ValueError("Missing tool file.")

        filename = uploaded_file.filename or ""
        source_bytes = uploaded_file.read()
        try:
            source_text = source_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("Tool files must be valid UTF-8 Python files.") from error

        return self.save_source_file(filename, source_text)

    def delete_tool_file(self, filename):
        normalized_filename = secure_filename(filename or "")
        if not normalized_filename:
            return

        tool_path = self.tools_directory / normalized_filename
        if tool_path.exists():
            tool_path.unlink()

    def _load_module(self, tool_path):
        spec = importlib.util.spec_from_file_location(
            self._build_module_name(tool_path),
            tool_path,
        )
        if not spec or not spec.loader:
            raise ImportError(f"Unable to load tool module from {tool_path.name}.")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _build_module_name(self, tool_path):
        stat = tool_path.stat()
        return f"horizone_lite_tool_{tool_path.stem}_{stat.st_mtime_ns}"

    def _seed_builtin_tools(self):
        for builtin_filename in self.BUILTIN_FILENAMES:
            source_path = self.package_tools_directory / builtin_filename
            if not source_path.exists():
                continue

            destination_path = self.tools_directory / builtin_filename
            if source_path.resolve() == destination_path.resolve():
                continue

            if destination_path.exists():
                continue

            shutil.copyfile(source_path, destination_path)
