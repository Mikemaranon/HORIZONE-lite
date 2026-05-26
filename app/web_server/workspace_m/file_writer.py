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

    def append(
        self,
        root_path,
        relative_path,
        content,
        *,
        ensure_newline_before=True,
        ensure_newline_after=False,
    ):
        target = self.path_guard.resolve_inside(root_path, relative_path)
        if not target.exists():
            raise ValueError("Workspace file does not exist; use workspace_write_file to create it")
        if not target.is_file():
            raise ValueError("Workspace path is not a file")

        existing_content = target.read_text(encoding="utf-8")
        append_content = str(content or "")
        if ensure_newline_before and existing_content and not existing_content.endswith("\n"):
            append_content = "\n" + append_content
        if ensure_newline_after and append_content and not append_content.endswith("\n"):
            append_content = append_content + "\n"

        next_content = existing_content + append_content
        encoded_content = next_content.encode("utf-8")
        if len(encoded_content) > self.max_bytes:
            raise ValueError("Workspace file content is too large")

        target.write_text(next_content, encoding="utf-8")

        return {
            "path": Path(relative_path).as_posix(),
            "size_bytes": len(encoded_content),
            "appended_bytes": len(append_content.encode("utf-8")),
            "created": False,
        }
