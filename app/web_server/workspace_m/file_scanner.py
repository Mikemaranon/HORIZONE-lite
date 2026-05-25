import fnmatch
import os
from pathlib import Path

from .path_guard import PathGuard


DEFAULT_IGNORED_NAMES = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}

LANGUAGE_BY_EXTENSION = {
    ".css": "css",
    ".html": "html",
    ".js": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".mjs": "javascript",
    ".py": "python",
    ".sh": "shell",
    ".sql": "sql",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".txt": "text",
    ".yml": "yaml",
    ".yaml": "yaml",
}


class FileScanner:
    def __init__(self, path_guard=None, max_files=5000, max_file_size=2 * 1024 * 1024):
        self.path_guard = path_guard or PathGuard()
        self.max_files = max_files
        self.max_file_size = max_file_size

    def scan(self, root_path):
        root = Path(self.path_guard.normalize_root(root_path))
        gitignore_patterns = self._load_gitignore_patterns(root)
        files = []

        for current_root, dir_names, file_names in os.walk(root, followlinks=False):
            current_path = Path(current_root)
            dir_names[:] = [
                name for name in dir_names
                if not self._is_ignored(root, current_path / name, True, gitignore_patterns)
            ]

            for file_name in file_names:
                file_path = current_path / file_name
                if self._is_ignored(root, file_path, False, gitignore_patterns):
                    continue

                try:
                    stat = file_path.stat()
                except OSError:
                    continue

                if stat.st_size > self.max_file_size:
                    continue

                files.append(self._file_record(root, file_path, stat))
                if len(files) >= self.max_files:
                    return files

        return files

    def _file_record(self, root, file_path, stat):
        relative_path = file_path.relative_to(root).as_posix()
        extension = file_path.suffix.lower()
        return {
            "path": relative_path,
            "kind": "file",
            "size_bytes": stat.st_size,
            "mtime": stat.st_mtime,
            "language": LANGUAGE_BY_EXTENSION.get(extension, ""),
            "is_ignored": False,
        }

    def _load_gitignore_patterns(self, root):
        gitignore_path = root / ".gitignore"
        if not gitignore_path.exists():
            return []

        patterns = []
        try:
            lines = gitignore_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return []

        for line in lines:
            pattern = line.strip()
            if not pattern or pattern.startswith("#") or pattern.startswith("!"):
                continue
            patterns.append(pattern)

        return patterns

    def _is_ignored(self, root, path, is_dir, gitignore_patterns):
        if path.name in DEFAULT_IGNORED_NAMES:
            return True

        if path.is_symlink():
            try:
                resolved = path.resolve()
                if root != resolved and root not in resolved.parents:
                    return True
            except OSError:
                return True

        relative_path = path.relative_to(root).as_posix()
        for pattern in gitignore_patterns:
            if self._matches_pattern(relative_path, path.name, pattern, is_dir):
                return True

        return False

    def _matches_pattern(self, relative_path, name, pattern, is_dir):
        normalized = pattern.strip("/")
        if not normalized:
            return False
        if pattern.endswith("/") and not is_dir:
            return False
        if "/" not in normalized and fnmatch.fnmatch(name, normalized):
            return True
        return fnmatch.fnmatch(relative_path, normalized) or fnmatch.fnmatch(relative_path, f"{normalized}/*")
