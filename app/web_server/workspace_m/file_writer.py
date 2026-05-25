from pathlib import Path

from .path_guard import PathGuard


class FileWriter:
    def __init__(self, path_guard=None, max_bytes=500 * 1024):
        self.path_guard = path_guard or PathGuard()
        self.max_bytes = max_bytes

    def write(self, root_path, relative_path, content, *, overwrite=False, create_dirs=False):
        target = self.path_guard.resolve_inside(root_path, relative_path)
        normalized_content = str(content or "")
        encoded_content = normalized_content.encode("utf-8")

        if len(encoded_content) > self.max_bytes:
            raise ValueError("Workspace file content is too large")

        existed = target.exists()

        if existed and not overwrite:
            raise ValueError("Workspace file already exists; set overwrite to true to replace it")
        if existed and not target.is_file():
            raise ValueError("Workspace path is not a file")

        parent = target.parent
        if not parent.exists():
            if not create_dirs:
                raise ValueError("Workspace parent directory does not exist")
            parent.mkdir(parents=True, exist_ok=True)

        target.write_text(normalized_content, encoding="utf-8")

        return {
            "path": Path(relative_path).as_posix(),
            "size_bytes": len(encoded_content),
            "created": not existed,
        }
