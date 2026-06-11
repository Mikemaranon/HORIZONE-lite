import os
import sys
from pathlib import Path

from flask import Flask


def bundle_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[2]


def configure_imports(root: Path) -> None:
    web_server_path = root / "app" / "web_server"
    if str(web_server_path) not in sys.path:
        sys.path.insert(0, str(web_server_path))


def create_app(root: Path) -> Flask:
    return Flask(
        __name__,
        template_folder=str(root / "app" / "web_app"),
        static_folder=str(root / "app" / "web_app" / "static"),
    )


def main() -> None:
    os.environ.setdefault("HORIZONE_DESKTOP", "1")
    root = bundle_root()
    configure_imports(root)

    import server as server_module

    app = create_app(root)
    server_module.Server(app)


if __name__ == "__main__":
    main()
