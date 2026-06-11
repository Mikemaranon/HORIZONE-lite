from __future__ import annotations

import argparse
import sys
from pathlib import Path


BUILDS_ROOT = Path(__file__).resolve().parents[1] / "builds"
sys.path.insert(0, str(BUILDS_ROOT))

from common import normalize_platform, run_desktop_build  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Legacy desktop build entrypoint. Prefer deploy/builds/build.py or "
            "deploy/builds/<platform>/build_desktop.py."
        )
    )
    parser.add_argument("--version", required=True, help="Release version.")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Stage and validate inputs without running PyInstaller or Tauri.",
    )
    parser.add_argument(
        "--skip-backend-freeze",
        action="store_true",
        help="Reuse an existing frozen backend and only run Tauri.",
    )
    parser.add_argument(
        "--preserve-release-root",
        action="store_true",
        help="Keep existing release artifacts before building.",
    )
    parser.add_argument(
        "--build-root",
        type=Path,
        default=None,
        help="Accepted for compatibility; platform builds now own build paths.",
    )
    parser.add_argument(
        "--release-root",
        type=Path,
        default=None,
        help="Accepted for compatibility; platform builds now own release paths.",
    )
    args = parser.parse_args(argv)

    if args.build_root or args.release_root:
        print("Ignoring legacy --build-root/--release-root; use deploy/builds/<platform>/build_desktop.py.")

    run_desktop_build(
        normalize_platform(),
        args.version,
        prepare_only=args.prepare_only,
        skip_backend_freeze=args.skip_backend_freeze,
        preserve_release_root=args.preserve_release_root,
    )


if __name__ == "__main__":
    main()
