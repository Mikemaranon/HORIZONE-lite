# HORIZONE Linux Build

## Preparacion

En Debian/Ubuntu:

```bash
python3 deploy/builds/linux/build_desktop.py setup
```

Si ya tienes paquetes del sistema instalados:

```bash
python3 deploy/builds/linux/build_desktop.py setup --skip-apt
```

Dependencias Python:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements/requirements-dev.txt
.venv/bin/pip install -r requirements/requirements-linux.txt
```

## Build

Validar staging:

```bash
.venv/bin/python deploy/builds/linux/build_desktop.py --version 0.1.0 --prepare-only
```

Build completo:

```bash
.venv/bin/python deploy/builds/linux/build_desktop.py --version 0.1.0
```

## Salida

```text
deploy/builds/linux/files/horizone_0.1.0_amd64.deb
```

Info rapida:

```bash
.venv/bin/python deploy/builds/linux/build_desktop.py info --version 0.1.0
```

