import ast
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_SERVER_ROOT = REPO_ROOT / "app" / "web_server"


def iter_python_files(path):
    return sorted(
        file_path
        for file_path in path.rglob("*.py")
        if "__pycache__" not in file_path.parts
    )


def imported_modules(tree):
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def string_literals(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


def read_ast(file_path):
    return ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_api_domains_do_not_import_sqlite(self):
        offenders = []
        for file_path in iter_python_files(APP_SERVER_ROOT / "api_m" / "domains"):
            modules = imported_modules(read_ast(file_path))
            if "sqlite3" in modules:
                offenders.append(str(file_path.relative_to(REPO_ROOT)))

        self.assertEqual(offenders, [])

    def test_data_repositories_do_not_import_flask(self):
        offenders = []
        for file_path in iter_python_files(APP_SERVER_ROOT / "data_m" / "db_methods"):
            modules = imported_modules(read_ast(file_path))
            if any(module == "flask" or module.startswith("flask.") for module in modules):
                offenders.append(str(file_path.relative_to(REPO_ROOT)))

        self.assertEqual(offenders, [])

    def test_model_providers_do_not_import_flask(self):
        offenders = []
        for file_path in iter_python_files(APP_SERVER_ROOT / "model_m" / "providers"):
            modules = imported_modules(read_ast(file_path))
            if any(module == "flask" or module.startswith("flask.") for module in modules):
                offenders.append(str(file_path.relative_to(REPO_ROOT)))

        self.assertEqual(offenders, [])

    def test_api_domains_do_not_contain_inline_sql(self):
        sql_tokens = ("SELECT ", "INSERT ", "UPDATE ", "DELETE FROM", "CREATE TABLE", "PRAGMA ")
        offenders = []
        for file_path in iter_python_files(APP_SERVER_ROOT / "api_m" / "domains"):
            tree = read_ast(file_path)
            for value in string_literals(tree):
                normalized = " ".join(value.upper().split())
                if any(token in normalized for token in sql_tokens):
                    offenders.append(str(file_path.relative_to(REPO_ROOT)))
                    break

        self.assertEqual(offenders, [])
