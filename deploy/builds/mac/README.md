# HORIZONE macOS Build

## Preparacion

Desde la raiz del repo:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements/requirements-dev.txt
.venv/bin/pip install -r requirements/requirements-mac.txt
```

Rust y Tauri deben estar disponibles:

```bash
cargo --version
cargo tauri --version
```

Si falta Tauri:

```bash
cargo install tauri-cli --version '^2'
```

## Runtime local

El build necesita un runtime local embebido. Usa una de estas opciones.

Con `llama-server` nativo:

```bash
export HORIZONE_LLAMA_CPP_BINARY=/ruta/al/llama-server
```

O con runtime Python:

```bash
.venv/bin/pip install -r requirements/requirements-runtime-llamacpp.txt
```

## Build

Validar staging:

```bash
.venv/bin/python deploy/builds/mac/build_desktop.py --version 0.1.0 --prepare-only
```

Build completo:

```bash
.venv/bin/python deploy/builds/mac/build_desktop.py --version 0.1.0
```

Rebuild rapido:

```bash
.venv/bin/python deploy/builds/mac/build_desktop.py --version 0.1.0 --skip-backend-freeze
```

## Salida

```text
deploy/builds/mac/files/horizone-0.1.0-macos-arm64.dmg
```

Info rapida:

```bash
.venv/bin/python deploy/builds/mac/build_desktop.py info --version 0.1.0
```

