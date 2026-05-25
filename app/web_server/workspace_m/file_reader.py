from pathlib import Path

from .path_guard import PathGuard


class FileReader:
    def __init__(self, path_guard=None, max_bytes=200 * 1024):
        self.path_guard = path_guard or PathGuard()
        self.max_bytes = max_bytes

    def read(self, root_path, relative_path):
        target = self.path_guard.resolve_inside(root_path, relative_path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError("Workspace file not found")

        size = target.stat().st_size
        if size > self.max_bytes:
            raise ValueError("Workspace file is too large to read")

        raw = target.read_bytes()
        if b"\x00" in raw[:2048]:
            raise ValueError("Workspace file appears to be binary")

        return {
            "path": Path(relative_path).as_posix(),
            "content": raw.decode("utf-8", errors="replace"),
            "size_bytes": size,
        }
