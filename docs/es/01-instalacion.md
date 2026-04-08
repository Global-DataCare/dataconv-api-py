# 01 - Instalación

## Requisitos

- Git.
- Python `>=3.11`.
- Acceso al archivo exportado por el software clínico (`.xlsx`).

## 1) Descargar repositorio

Si todavía no lo tienes:

```bash
git clone <URL-DEL-REPO> dataconv-api-py
cd dataconv-api-py
```

Si ya lo tienes local:

```bash
cd /ruta/a/dataconv-api-py
```

## 2) Verificar Python

```bash
python3.11 --version
```

Debe devolver `3.11` o superior.

## 3) (Recomendado) Entorno virtual

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python --version
python -m pip install --upgrade pip setuptools wheel
```

Importante:

- Usa siempre `python -m pip` (no `pip` suelto) para evitar mezclar intérpretes.
- Si `python3.11` no está en PATH, comprueba primero `which python3` y `python3 --version` antes de crear `.venv`.
- Si ves `UNKNOWN-0.0.0` o `does not provide the extra 'api'`, tu `pip/setuptools` es antiguo o viene del Python de Xcode. Activa `.venv` y repite el upgrade anterior.

## 4) API local

Para levantar el servicio HTTP completo en local instala extras de API:

Instalación:

```bash
source .venv/bin/activate
python -m pip install -e ".[api,excel]"
cp env.local.example .env.local
```

### Modo local `mem` (worker embebido): 1 terminal

Con providers en memoria (`mem`), la API arranca worker embebido automáticamente:

```bash
source .venv/bin/activate
./scripts/run-api-local.sh
```

### Modo no embebido (`gcloud`/producción): 2 terminales (solo ejecución manual local)

Arranque:

Terminal 1:

```bash
source .venv/bin/activate
./scripts/run-api-local.sh
```

Terminal 2:

```bash
source .venv/bin/activate
./scripts/run-worker-local.sh
```

Nota:

- Esto aplica a ejecución local manual cuando no se usa worker embebido (`mem`).
- En Docker local no hace falta abrir dos terminales manuales para API/worker.
- En Kubernetes/cloud, API y worker se ejecutan como workloads gestionados por el orquestador.

Importante:

- La activación de `.venv` no se comparte entre terminales.
- Si abres una terminal nueva, repite `source .venv/bin/activate`.
- Swagger por defecto queda en `http://127.0.0.1:{LOCAL_PORT}/api-docs` (usa `LOCAL_PORT` y, en Docker, `DOCKER_PORT` para el host).

## 5) Ejecutar sin instalación de dependencias extra

Este proyecto funciona con librería estándar para lectura XLSX, así que puedes usar directamente:

```bash
PYTHONPATH=src python3.11 -m adapter_ingestion --help
```

Si prefieres instalar el comando de consola:

```bash
python -m pip install -e .
adapter-ingestion --help
```

## 6) Validación rápida

```bash
python3.11 -m unittest discover -s tests
```
