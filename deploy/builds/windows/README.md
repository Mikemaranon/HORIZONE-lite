# HORIZONE Windows Build

## Preparacion

Desde PowerShell o la terminal que uses para el repo:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements\requirements-dev.txt
.venv\Scripts\python -m pip install -r requirements\requirements-windows.txt
```

Rust y Tauri deben estar disponibles:

```powershell
cargo --version
cargo tauri --version
```

Si falta Tauri:

```powershell
cargo install tauri-cli --version "^2"
```

## Build

Validar staging:

```powershell
.venv\Scripts\python deploy\builds\windows\build_desktop.py --version 0.1.0 --prepare-only
```

Build completo:

```powershell
.venv\Scripts\python deploy\builds\windows\build_desktop.py --version 0.1.0
```

## Salida

```text
deploy/builds/windows/files/horizone-0.1.0-windows-x64.exe
```

Info rapida:

```powershell
.venv\Scripts\python deploy\builds\windows\build_desktop.py info --version 0.1.0
```

