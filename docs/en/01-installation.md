# 01 - Installation

## Requirements

- Git
- Python `>=3.11`
- Access to the exported clinical spreadsheet (`.xlsx`)

## 1) Clone or enter the repository

If you do not have the repository yet:

```bash
git clone <REPO-URL> dataconv-api-py
cd dataconv-api-py
```

If you already have it locally:

```bash
cd /path/to/dataconv-api-py
```

## 2) Verify Python

```bash
python3.11 --version
```

The command must report Python 3.11 or newer.

## 3) Create a virtual environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python --version
python -m pip install --upgrade pip setuptools wheel
```

Important notes:

- Always use `python -m pip` rather than a bare `pip` command.
- If `python3.11` is not available in `PATH`, verify `which python3` and `python3 --version` before creating `.venv`.
- If you see `UNKNOWN-0.0.0` or `does not provide the extra 'api'`, your `pip` or `setuptools` is too old or you are using the wrong interpreter.

## 4) Install the local API workflow

```bash
source .venv/bin/activate
python -m pip install -e ".[api,excel]"
cp env.local.example .env.local
```

### Embedded worker mode (`mem`)

```bash
source .venv/bin/activate
./scripts/run-api-local.sh
```

### Split API and worker mode

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

Notes:

- Activation does not carry over across terminals.
- Swagger is available at `http://127.0.0.1:{LOCAL_PORT}/api-docs`.

## 5) Run without installing optional dependencies

The XLSX reader can run on the standard library path configuration:

```bash
PYTHONPATH=src python3.11 -m adapter_ingestion --help
```

If you prefer the console entry point:

```bash
python -m pip install -e .
adapter-ingestion --help
```

## 6) Quick validation

```bash
python3.11 -m unittest discover -s tests
```
