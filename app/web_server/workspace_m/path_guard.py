from pathlib import Path


class PathGuardError(ValueError):
    pass


class PathGuard:
    def normalize_root(self, root_path):
        if not root_path or not str(root_path).strip():
            raise PathGuardError("Missing workspace path")

        root = Path(str(root_path)).expanduser().resolve()
        if not root.exists():
            raise PathGuardError("Workspace path does not exist")
        if not root.is_dir():
            raise PathGuardError("Workspace path must be a directory")

        return str(root)

    def resolve_inside(self, root_path, relative_path=""):
        root = Path(self.normalize_root(root_path))
        relative = Path(str(relative_path or ""))

        if relative.is_absolute():
            raise PathGuardError("Workspace paths must be relative")

        target = (root / relative).resolve()
        if target != root and root not in target.parents:
            raise PathGuardError("Path is outside the workspace")

        return target

    def to_relative(self, root_path, target_path):
        root = Path(self.normalize_root(root_path))
        target = Path(target_path).resolve()

        if target != root and root not in target.parents:
            raise PathGuardError("Path is outside the workspace")

        return target.relative_to(root).as_posix()
