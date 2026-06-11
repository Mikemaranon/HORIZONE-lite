import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import ROOT, ensure_platform, platform_files_root, run_desktop_build


SYSTEM_PACKAGES = [
    "build-essential",
    "pkg-config",
    "libglib2.0-dev",
    "libgtk-3-dev",
    "libwebkit2gtk-4.1-dev",
    "libxdo-dev",
    "libssl-dev",
    "libayatana-appindicator3-dev",
    "librsvg2-dev",
    "libsoup-3.0-dev",
    "python3-venv",
    "python3-pip",
    "nodejs",
    "npm",
    "dpkg-dev",
    "fakeroot",
    "curl",
]


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, cwd=str(ROOT))


def sudo_prefix() -> list[str]:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return []
    return ["sudo"]


def prepare_debian(skip_apt: bool) -> None:
    if not skip_apt:
        prefix = sudo_prefix()
        run(prefix + ["apt-get", "update"])
        run(prefix + ["apt-get", "install", "-y", *SYSTEM_PACKAGES])

    cargo = shutil.which("cargo") or str(Path.home() / ".cargo" / "bin" / "cargo")
    if shutil.which("cargo") is None and not Path(cargo).exists():
        raise SystemExit("Rust/Cargo is missing. Install rustup before building HORIZONE.")

    print("Linux build environment is ready.")


def print_release_path(version: str) -> None:
    files_root = platform_files_root("linux")
    print(f"Expected Linux release directory: {files_root}")
    print(f"Expected deb name: horizone_{version}_amd64.deb")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the HORIZONE desktop app for Linux.")
    parser.add_argument("--version", required=True, help="Release version.")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Stage and validate inputs without running native packagers.",
    )
    parser.add_argument(
        "--skip-backend-freeze",
        action="store_true",
        help="Reuse deploy/desktop/dist/backend/horizone-backend and only run Tauri.",
    )
    return parser


def command_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Linux desktop build helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup_parser = subparsers.add_parser("setup", help="Prepare a Debian/Ubuntu build environment.")
    setup_parser.add_argument(
        "--skip-apt",
        action="store_true",
        help="Skip apt package installation and only validate local tools.",
    )

    info_parser = subparsers.add_parser("info", help="Print expected release paths.")
    info_parser.add_argument("--version", required=True, help="Release version.")

    return parser


def main(argv: list[str] | None = None) -> None:
    args_list = list(argv if argv is not None else sys.argv[1:])
    if args_list[:1] in (["setup"], ["info"]):
        args = command_arg_parser().parse_args(args_list)
        ensure_platform("linux")
        if args.command == "setup":
            prepare_debian(args.skip_apt)
            return
        print_release_path(args.version)
        return

    args = build_arg_parser().parse_args(args_list)
    ensure_platform("linux")
    run_desktop_build(
        "linux",
        args.version,
        prepare_only=args.prepare_only,
        skip_backend_freeze=args.skip_backend_freeze,
    )


if __name__ == "__main__":
    main()
