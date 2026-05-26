from .file_reader import FileReader
from .file_scanner import FileScanner
from .file_writer import FileWriter
from .path_guard import PathGuard


class WorkspaceManager:
    def __init__(self, path_guard=None, file_scanner=None, file_reader=None, file_writer=None):
        self.path_guard = path_guard or PathGuard()
        self.file_scanner = file_scanner or FileScanner(self.path_guard)
        self.file_reader = file_reader or FileReader(self.path_guard)
        self.file_writer = file_writer or FileWriter(self.path_guard)

    def normalize_root(self, root_path):
        return self.path_guard.normalize_root(root_path)

    def scan(self, root_path):
        return self.file_scanner.scan(root_path)

    def read_file(self, root_path, relative_path):
        return self.file_reader.read(root_path, relative_path)

    def write_file(self, root_path, relative_path, content, *, overwrite=False, create_dirs=False):
        return self.file_writer.write(
            root_path,
            relative_path,
            content,
            overwrite=overwrite,
            create_dirs=create_dirs,
        )

    def append_file(
        self,
        root_path,
        relative_path,
        content,
        *,
        ensure_newline_before=True,
        ensure_newline_after=False,
    ):
        return self.file_writer.append(
            root_path,
            relative_path,
            content,
            ensure_newline_before=ensure_newline_before,
            ensure_newline_after=ensure_newline_after,
        )

    def search(self, root_path, indexed_files, query, limit=50):
        normalized_query = (query or "").strip()
        if not normalized_query:
            raise ValueError("Missing search query")

        matches = []
        lowered_query = normalized_query.lower()

        for indexed_file in indexed_files:
            if len(matches) >= limit:
                break

            path = indexed_file["path"]
            try:
                file_payload = self.read_file(root_path, path)
            except (FileNotFoundError, OSError, UnicodeError, ValueError):
                continue

            for line_number, line in enumerate(file_payload["content"].splitlines(), start=1):
                if lowered_query in line.lower():
                    matches.append({
                        "path": path,
                        "line": line_number,
                        "preview": line.strip()[:240],
                    })
                    if len(matches) >= limit:
                        break

        return matches
