import ast
import importlib.util
import os
import shutil
from pathlib import Path

from werkzeug.utils import secure_filename

from .tool_contract import TOOL_RISK_LEVELS, validate_tool_module


class ToolLoader:
    BUILTIN_FILENAMES = {
        "current_date.py",
        "web_search.py",
    }
    MAX_CUSTOM_TOOL_BYTES = 64 * 1024
    BLOCKED_CUSTOM_IMPORTS = {
        "ctypes",
        "multiprocessing",
        "os",
        "pathlib",
        "shutil",
        "socket",
        "subprocess",
        "sys",
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

        normalized_source = str(source_text or "")
        self._validate_custom_source(normalized_source)

        destination = self.tools_directory / normalized_filename
        if destination.exists():
            raise ValueError("A tool with that filename already exists.")

        destination.write_text(normalized_source, encoding="utf-8")
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

    def _validate_custom_source(self, source_text):
        source_bytes = source_text.encode("utf-8")
        if len(source_bytes) > self.MAX_CUSTOM_TOOL_BYTES:
            raise ValueError("Tool source is too large.")

        try:
            tree = ast.parse(source_text)
        except SyntaxError as error:
            raise ValueError("Tool source must be valid Python.") from error

        risk_level = self._extract_string_constant(tree, "TOOL_RISK_LEVEL")
        if not risk_level:
            raise ValueError("Custom tools must define TOOL_RISK_LEVEL explicitly.")
        if risk_level not in TOOL_RISK_LEVELS:
            raise ValueError(
                "TOOL_RISK_LEVEL must be one of: "
                + ", ".join(sorted(TOOL_RISK_LEVELS))
            )

        blocked_imports = self._find_blocked_imports(tree)
        if blocked_imports:
            raise ValueError(
                "Custom tool imports are not allowed for: "
                + ", ".join(sorted(blocked_imports))
            )

    def _extract_string_constant(self, tree, variable_name):
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == variable_name for target in node.targets):
                continue
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value.strip()
        return ""

    def _find_blocked_imports(self, tree):
        blocked_imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_name = alias.name.split(".", 1)[0]
                    if root_name in self.BLOCKED_CUSTOM_IMPORTS:
                        blocked_imports.add(root_name)
            elif isinstance(node, ast.ImportFrom):
                root_name = (node.module or "").split(".", 1)[0]
                if root_name in self.BLOCKED_CUSTOM_IMPORTS:
                    blocked_imports.add(root_name)
        return blocked_imports

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
