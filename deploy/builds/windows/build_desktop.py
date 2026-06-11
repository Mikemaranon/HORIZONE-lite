import argparse
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import ensure_platform, platform_files_root, run_desktop_build


def print_release_path(version: str) -> None:
    files_root = platform_files_root("windows")
    print(f"Expected Windows release directory: {files_root}")
    print(f"Expected installer name: horizone-{version}-windows-x64.exe")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the HORIZONE desktop app for Windows.")
    parser.add_argument("--version", required=True, help="Release version.")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Stage and validate inputs without running PyInstaller or Tauri.",
    )
    parser.add_argument(
        "--skip-backend-freeze",
        action="store_true",
        help="Reuse deploy/desktop/dist/backend/horizone-backend.exe and only run Tauri.",
    )
    return parser


def command_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Windows desktop build helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    info_parser = subparsers.add_parser("info", help="Print expected release paths.")
    info_parser.add_argument("--version", required=True, help="Release version.")

    return parser


def main(argv: list[str] | None = None) -> None:
    args_list = list(argv if argv is not None else sys.argv[1:])
    if args_list[:1] == ["info"]:
        args = command_arg_parser().parse_args(args_list)
        ensure_platform("windows")
        print_release_path(args.version)
        return

    args = build_arg_parser().parse_args(args_list)

    ensure_platform("windows")
    run_desktop_build(
        "windows",
        args.version,
        prepare_only=args.prepare_only,
        skip_backend_freeze=args.skip_backend_freeze,
    )


if __name__ == "__main__":
    main()
