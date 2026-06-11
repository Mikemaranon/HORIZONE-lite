# HORIZONE Builds

Este directorio es la entrada canonica para empaquetar HORIZONE.

## Estructura

```text
deploy/builds/
  build.py
  common.py
  mac/
    build_desktop.py
    README.md
    files/
  linux/
    build_desktop.py
    README.md
    files/
  windows/
    build_desktop.py
    README.md
    files/
```

## Comando global

Desde la raiz del repo:

```bash
.venv/bin/python deploy/builds/build.py --version 0.1.0
```

Validacion sin ejecutar PyInstaller ni Tauri:

```bash
.venv/bin/python deploy/builds/build.py --version 0.1.0 --prepare-only
```

Rebuild rapido reutilizando el backend congelado:

```bash
.venv/bin/python deploy/builds/build.py --version 0.1.0 --skip-backend-freeze
```

## Responsabilidades

- `build.py`: detecta la plataforma actual y llama al script correcto.
- `common.py`: contiene utilidades compartidas de staging, PyInstaller, runtime, Tauri y copia de artefactos.
- `mac/build_desktop.py`: flujo principal para macOS.
- `linux/build_desktop.py`: flujo principal para Linux.
- `windows/build_desktop.py`: flujo principal para Windows.
- `deploy/desktop/`: contiene el codigo y recursos de la app desktop, pero no es la entrada principal de build.

