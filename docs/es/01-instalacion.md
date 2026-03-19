# 01 - Instalación

## Requisitos

- Git.
- Python `>=3.8`.
- Acceso al archivo exportado por el software clínico (`.xlsx`).

## 1) Descargar repositorio

Si todavía no lo tienes:

```bash
git clone <URL-DEL-REPO> adapter-ingestion-py
cd adapter-ingestion-py
```

Si ya lo tienes local:

```bash
cd /ruta/a/adapter-ingestion-py
```

## 2) Verificar Python

```bash
python3 --version
```

Debe devolver `3.8` o superior.

## 3) (Recomendado) Entorno virtual

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

Importante:

- Usa siempre `python -m pip` (no `pip` suelto) para evitar mezclar intérpretes.
- Si ves `UNKNOWN-0.0.0` o `does not provide the extra 'api'`, tu `pip/setuptools` es antiguo o viene del Python de Xcode. Activa `.venv` y repite el upgrade anterior.

## 4) API local (dos terminales)

Para levantar el servicio HTTP completo en local necesitas instalar extras de API y ejecutar dos procesos:

- `preconversion-api`
- `preconversion-worker`

Instalación:

```bash
source .venv/bin/activate
python -m pip install -e ".[api,excel]"
cp .env.local.example .env.local
```

Arranque:

Terminal 1:

```bash
source .venv/bin/activate
preconversion-api
```

Terminal 2:

```bash
source .venv/bin/activate
preconversion-worker
```

Importante:

- La activación de `.venv` no se comparte entre terminales.
- Si abres una terminal nueva, repite `source .venv/bin/activate`.
- Swagger queda en `http://127.0.0.1:8080/api-docs`.

## 5) Ejecutar sin instalación de dependencias extra

Este proyecto funciona con librería estándar para lectura XLSX, así que puedes usar directamente:

```bash
PYTHONPATH=src python3 -m adapter_ingestion --help
```

Si prefieres instalar el comando de consola:

```bash
python -m pip install -e .
adapter-ingestion --help
```

## 6) Validación rápida

```bash
python3 -m unittest discover -s tests
```
