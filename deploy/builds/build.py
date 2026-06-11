import argparse
import sys

from common import (
    SUPPORTED_TARGETS,
    normalize_platform,
    platform_script_path,
    prepare_files_root,
    run,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Build HORIZONE desktop packages for the current operating system."
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Version label used in the release artifact names.",
    )
    parser.add_argument(
        "--target",
        choices=SUPPORTED_TARGETS,
        default="desktop",
        help="Build target. HORIZONE currently ships as one integrated desktop app.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Validate and stage build inputs without running PyInstaller or Tauri.",
    )
    parser.add_argument(
        "--skip-backend-freeze",
        action="store_true",
        help="Reuse an existing frozen backend and only rebuild the Tauri shell.",
    )
    args = parser.parse_args(argv)

    platform_name = normalize_platform()
    prepare_files_root(platform_name, (args.target,))

    command = [
        sys.executable,
        str(platform_script_path(platform_name, args.target)),
        "--version",
        args.version,
    ]
    if args.prepare_only:
        command.append("--prepare-only")
    if args.skip_backend_freeze:
        command.append("--skip-backend-freeze")
    run(command)


if __name__ == "__main__":
    main()
