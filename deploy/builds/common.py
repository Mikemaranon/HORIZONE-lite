from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEPLOY_ROOT = ROOT / "deploy"
DESKTOP_ROOT = DEPLOY_ROOT / "desktop"
BUILDS_ROOT = DEPLOY_ROOT / "builds"
APP_ROOT = ROOT / "app"
WEB_SERVER_ROOT = APP_ROOT / "web_server"
WEB_APP_ROOT = APP_ROOT / "web_app"
REQUIREMENTS_ROOT = ROOT / "requirements"
BACKEND_DIST_ROOT = DESKTOP_ROOT / "dist" / "backend"
RUNTIME_DIST_ROOT = DESKTOP_ROOT / "dist" / "runtime"

NATIVE_LLAMA_SERVER_NAME = "llama-server"
PYTHON_LLAMA_SERVER_NAME = "horizone-llama-server"

PLATFORM_TO_DIR = {
    "windows": "windows",
    "linux": "linux",
    "macos": "mac",
}

PLATFORM_LABELS = {
    "windows": "Windows",
    "linux": "Linux",
    "macos": "macOS",
}

SUPPORTED_TARGETS = ("desktop",)

MACOS_MLX_MODULES = {
    "mlx_lm": "mlx-lm",
    "mlx": "mlx",
}

MACOS_MLX_PYINSTALLER_PACKAGES = ("mlx_lm", "mlx")

STAGE_IGNORE = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    ".DS_Store",
    "flask.db",
)


def normalize_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def build_directory_name(platform_name: str | None = None) -> str:
    platform_key = platform_name or normalize_platform()
    return PLATFORM_TO_DIR[platform_key]


def platform_files_root(platform_name: str) -> Path:
    return BUILDS_ROOT / build_directory_name(platform_name) / "files"


def target_output_root(platform_name: str, target: str) -> Path:
    return BUILDS_ROOT / build_directory_name(platform_name) / target


def platform_script_path(platform_name: str, target: str) -> Path:
    return BUILDS_ROOT / build_directory_name(platform_name) / f"build_{target}.py"


def desktop_builder_path() -> Path:
    return DESKTOP_ROOT / "build_release.py"


def runtime_env() -> dict[str, str]:
    env = dict(os.environ)
    cargo_bin = Path.home() / ".cargo" / "bin"
    if cargo_bin.exists():
        path_entries = env.get("PATH", "").split(os.pathsep)
        cargo_entry = str(cargo_bin)
        if cargo_entry not in path_entries:
            env["PATH"] = os.pathsep.join([cargo_entry, *path_entries])
    return env


def run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, check=True, cwd=str(cwd or ROOT), env=runtime_env())


def remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
        return
    if path.exists() or path.is_symlink():
        path.unlink()


def prepare_files_root(platform_name: str, targets: tuple[str, ...]) -> Path:
    files_root = platform_files_root(platform_name)
    files_root.mkdir(parents=True, exist_ok=True)
    if len(targets) > 1:
        for candidate in files_root.iterdir():
            remove_path(candidate)
        return files_root

    for candidate in files_root.iterdir():
        if candidate.name.startswith("horizone-") or candidate.name.startswith("horizone_"):
            remove_path(candidate)
    return files_root


def ensure_platform(expected_platform: str) -> None:
    current_platform = normalize_platform()
    if current_platform == expected_platform:
        return

    expected_label = PLATFORM_LABELS[expected_platform]
    current_label = PLATFORM_LABELS[current_platform]
    raise SystemExit(
        f"This build entrypoint targets {expected_label} and must run on "
        f"{expected_label}. Current platform: {current_label}."
    )


def copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=STAGE_IGNORE)


def executable_name(name: str) -> str:
    return f"{name}.exe" if sys.platform.startswith("win") else name


def validate_desktop_inputs() -> None:
    required_paths = [
        WEB_SERVER_ROOT / "main.py",
        WEB_SERVER_ROOT / "server.py",
        WEB_APP_ROOT / "index.html",
        WEB_APP_ROOT / "login.html",
        REQUIREMENTS_ROOT / "requirements-core.txt",
        DESKTOP_ROOT / "backend_entry.py",
        DESKTOP_ROOT / "src-tauri" / "Cargo.toml",
        DESKTOP_ROOT / "src-tauri" / "tauri.conf.json",
        DESKTOP_ROOT / "src-tauri" / "src" / "main.rs",
    ]

    missing = [str(path.relative_to(ROOT)) for path in required_paths if not path.exists()]
    if missing:
        formatted = "\n".join(f"- {path}" for path in missing)
        raise SystemExit(f"Cannot build HORIZONE desktop package. Missing inputs:\n{formatted}")


def validate_runtime_source() -> None:
    if resolve_native_llama_server_binary() or has_llama_cpp_python_server():
        return

    raise SystemExit(
        "Cannot build HORIZONE desktop package without an embedded HORIZONE runtime. "
        "Install llama.cpp's llama-server and set HORIZONE_LLAMA_CPP_BINARY, "
        "or install requirements/requirements-runtime-llamacpp.txt in the active build environment."
    )


def has_python_module(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except ModuleNotFoundError:
        return False


def ensure_macos_mlx_dependencies() -> None:
    missing_packages = [
        package_name
        for module_name, package_name in MACOS_MLX_MODULES.items()
        if not has_python_module(module_name)
    ]
    if not missing_packages:
        return

    formatted_packages = ", ".join(missing_packages)
    raise SystemExit(
        "macOS desktop builds must be frozen from an environment with MLX installed "
        "so the packaged app can use the MLX provider. "
        f"Missing: {formatted_packages}. "
        "Run `.venv/bin/pip install -r requirements/requirements-mac.txt` and rebuild "
        "without `--skip-backend-freeze`."
    )


def prepare_desktop_stage(build_root: Path, version: str, platform_name: str) -> Path:
    stage_root = build_root / "stage"
    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage_root.mkdir(parents=True, exist_ok=True)

    copy_tree(APP_ROOT, stage_root / "app")
    copy_tree(REQUIREMENTS_ROOT, stage_root / "requirements")
    shutil.copy2(DESKTOP_ROOT / "backend_entry.py", stage_root / "backend_entry.py")

    manifest = {
        "product": "HORIZONE",
        "version": version,
        "platform": platform_name,
        "backend_entry": "backend_entry.py",
        "web_server": "app/web_server",
        "web_app": "app/web_app",
    }
    (stage_root / "desktop-build-manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return stage_root


def web_server_module_names(web_server_root: Path) -> list[str]:
    module_names = []
    for path in sorted(web_server_root.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        relative = path.relative_to(web_server_root).with_suffix("")
        module_names.append(".".join(relative.parts))
    return module_names


def pyinstaller_backend_command(
    stage_root: Path,
    build_root: Path,
    platform_name: str | None = None,
) -> list[str]:
    separator = ";" if sys.platform.startswith("win") else ":"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "horizone-backend",
        "--distpath",
        str(BACKEND_DIST_ROOT),
        "--workpath",
        str(build_root / "pyinstaller-work"),
        "--specpath",
        str(build_root / "pyinstaller-spec"),
        "--paths",
        str(stage_root / "app" / "web_server"),
        "--add-data",
        f"{stage_root / 'app'}{separator}app",
        "--add-data",
        f"{stage_root / 'requirements'}{separator}requirements",
    ]
    if platform_name == "macos":
        for package_name in MACOS_MLX_PYINSTALLER_PACKAGES:
            command.extend(["--collect-all", package_name])

    for module_name in web_server_module_names(stage_root / "app" / "web_server"):
        command.extend(["--hidden-import", module_name])
    command.append(str(stage_root / "backend_entry.py"))
    return command


def ensure_pyinstaller_available(message: str) -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError as error:
        raise SystemExit(message) from error


def freeze_desktop_backend(stage_root: Path, build_root: Path, platform_name: str) -> None:
    ensure_pyinstaller_available(
        "PyInstaller is required for a full desktop build. "
        "Install it in the active environment or run with --prepare-only."
    )
    if platform_name == "macos":
        ensure_macos_mlx_dependencies()

    if BACKEND_DIST_ROOT.exists():
        shutil.rmtree(BACKEND_DIST_ROOT)
    run(pyinstaller_backend_command(stage_root, build_root, platform_name))


def ensure_frozen_backend_exists() -> None:
    executable_path = BACKEND_DIST_ROOT / executable_name("horizone-backend")
    if not executable_path.exists():
        raise SystemExit(
            f"Frozen backend not found: {executable_path}. "
            "Run without --skip-backend-freeze first."
        )


def resolve_native_llama_server_binary() -> Path | None:
    configured = os.environ.get("HORIZONE_LLAMA_CPP_BINARY", "").strip()
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_file() else None

    discovered = shutil.which(executable_name(NATIVE_LLAMA_SERVER_NAME))
    if discovered:
        return Path(discovered)

    if not sys.platform.startswith("win"):
        discovered = shutil.which(NATIVE_LLAMA_SERVER_NAME)
        if discovered:
            return Path(discovered)

    return None


def has_llama_cpp_python_server() -> bool:
    try:
        return importlib.util.find_spec("llama_cpp.server.__main__") is not None
    except ModuleNotFoundError:
        return False


def make_executable(path: Path) -> None:
    if not sys.platform.startswith("win"):
        path.chmod(path.stat().st_mode | 0o755)


def write_runtime_manifest(*, kind: str, executable: str, source: str) -> None:
    manifest = {
        "product": "HORIZONE runtime",
        "kind": kind,
        "executable": executable,
        "source": source,
    }
    (RUNTIME_DIST_ROOT / "runtime-manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


def bundle_native_llama_server(source: Path) -> None:
    destination = RUNTIME_DIST_ROOT / executable_name(NATIVE_LLAMA_SERVER_NAME)
    shutil.copy2(source, destination)
    make_executable(destination)
    write_runtime_manifest(kind="native", executable=destination.name, source=str(source))
    print(f"Bundled native HORIZONE runtime: {destination}")


def freeze_llama_cpp_python_server(build_root: Path) -> None:
    ensure_pyinstaller_available(
        "PyInstaller is required to freeze the embedded HORIZONE runtime. "
        "Install it in the active environment."
    )
    entrypoint = build_root / "horizone_llama_server_entry.py"
    entrypoint.write_text(
        "from llama_cpp.server.__main__ import main\n\n"
        "if __name__ == \"__main__\":\n"
        "    main()\n",
        encoding="utf-8",
    )
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        PYTHON_LLAMA_SERVER_NAME,
        "--distpath",
        str(RUNTIME_DIST_ROOT),
        "--workpath",
        str(build_root / "runtime-pyinstaller-work"),
        "--specpath",
        str(build_root / "runtime-pyinstaller-spec"),
        "--collect-all",
        "llama_cpp",
        "--collect-submodules",
        "llama_cpp.server",
        "--collect-submodules",
        "uvicorn",
        "--collect-submodules",
        "fastapi",
        "--collect-submodules",
        "starlette",
        "--collect-submodules",
        "pydantic_settings",
        str(entrypoint),
    ]
    run(command)
    destination = RUNTIME_DIST_ROOT / executable_name(PYTHON_LLAMA_SERVER_NAME)
    if not destination.exists():
        raise SystemExit(f"Embedded HORIZONE runtime was not produced: {destination}")
    make_executable(destination)
    write_runtime_manifest(kind="python", executable=destination.name, source="llama_cpp.server")
    print(f"Bundled Python HORIZONE runtime: {destination}")


def prepare_runtime_bundle(build_root: Path) -> None:
    if RUNTIME_DIST_ROOT.exists():
        shutil.rmtree(RUNTIME_DIST_ROOT)
    RUNTIME_DIST_ROOT.mkdir(parents=True, exist_ok=True)

    native_binary = resolve_native_llama_server_binary()
    if native_binary:
        bundle_native_llama_server(native_binary)
        return

    if has_llama_cpp_python_server():
        freeze_llama_cpp_python_server(build_root)
        return

    validate_runtime_source()


def build_tauri_desktop() -> None:
    if shutil.which("cargo") is None:
        raise SystemExit("Cargo is required for the Tauri build. Install Rust or run with --prepare-only.")
    run(["cargo", "tauri", "build"], cwd=DESKTOP_ROOT / "src-tauri")


def clean_tauri_bundle_outputs(platform_name: str) -> None:
    bundle_root = DESKTOP_ROOT / "src-tauri" / "target" / "release" / "bundle"
    if platform_name == "macos":
        remove_path(bundle_root / "macos" / "HORIZONE.app")
        remove_path(bundle_root / "dmg")


def verify_macos_app_signature() -> None:
    app_bundle = DESKTOP_ROOT / "src-tauri" / "target" / "release" / "bundle" / "macos" / "HORIZONE.app"
    if not app_bundle.exists():
        raise SystemExit(f"macOS app bundle was not produced: {app_bundle}")

    run(["codesign", "--verify", "--deep", "--strict", "--verbose=4", str(app_bundle)])


def normalized_artifact_name(platform_name: str, artifact: Path, version: str) -> str:
    if platform_name == "macos" and artifact.suffix == ".dmg":
        return f"horizone-{version}-macos-arm64.dmg"
    if platform_name == "windows" and artifact.suffix in {".exe", ".msi"}:
        return f"horizone-{version}-windows-x64{artifact.suffix}"
    if platform_name == "linux" and artifact.suffix == ".deb":
        return f"horizone_{version}_amd64.deb"
    if platform_name == "linux" and artifact.suffix == ".AppImage":
        return f"horizone-{version}-linux-x64.AppImage"
    return f"horizone-{version}-{platform_name}{artifact.suffix}"


def copy_release_artifacts(platform_name: str, release_root: Path, version: str) -> None:
    bundle_root = DESKTOP_ROOT / "src-tauri" / "target" / "release" / "bundle"
    if not bundle_root.exists():
        raise SystemExit(f"Tauri bundle output not found: {bundle_root}")

    release_root.mkdir(parents=True, exist_ok=True)
    patterns = ("*.dmg", "*.exe", "*.msi", "*.deb", "*.AppImage", "*.rpm", "*.tar.gz")
    copied = []
    for pattern in patterns:
        for artifact in bundle_root.rglob(pattern):
            destination = release_root / normalized_artifact_name(platform_name, artifact, version)
            shutil.copy2(artifact, destination)
            copied.append(destination)

    if not copied:
        raise SystemExit(f"No Tauri release artifacts found under {bundle_root}")

    print("Release artifacts:")
    for artifact in copied:
        print(f"- {artifact}")


def run_desktop_build(
    platform_name: str,
    version: str,
    *,
    prepare_only: bool = False,
    skip_backend_freeze: bool = False,
    preserve_release_root: bool = True,
) -> None:
    validate_desktop_inputs()
    validate_runtime_source()

    build_root = (target_output_root(platform_name, "desktop") / "build").resolve()
    release_root = platform_files_root(platform_name).resolve()

    if not preserve_release_root and release_root.exists():
        shutil.rmtree(release_root)
    release_root.mkdir(parents=True, exist_ok=True)
    build_root.mkdir(parents=True, exist_ok=True)

    stage_root = prepare_desktop_stage(build_root, version, platform_name)
    print(f"Prepared desktop build stage: {stage_root}")

    if prepare_only:
        print("Prepare-only mode complete. Native packagers were not executed.")
        return

    if skip_backend_freeze:
        ensure_frozen_backend_exists()
    else:
        freeze_desktop_backend(stage_root, build_root, platform_name)
    prepare_runtime_bundle(build_root)
    clean_tauri_bundle_outputs(platform_name)
    build_tauri_desktop()
    if platform_name == "macos":
        verify_macos_app_signature()
    copy_release_artifacts(platform_name, release_root, version)
