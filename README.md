# adapter-ingestion-py

Idioma principal:

- Español: [README_es.md](README_es.md)
- English: pending (`README_en.md`)

## Inicio rápido local (API + worker)

Preparación:

```bash
cd /Users/fernando/GITS/gdc-workspace/adapter-ingestion-py

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e ".[api,excel]"

cp .env.local.example .env.local
```

Arranque en dos terminales separadas.
Importante: si abres una terminal nueva, debes volver a ejecutar `source .venv/bin/activate` en esa terminal.

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

Swagger local:

- `http://127.0.0.1:8080/api-docs`

Más detalle:

- Español: [INTEGRATORS_GUIDE.md](INTEGRATORS_GUIDE.md)
- Español: [README_es.md](README_es.md)
- Español: [docs/es/API_DEVELOPMENT_GUIDE.md](docs/es/API_DEVELOPMENT_GUIDE.md)

Flujo copy/paste recomendado para integradores:

- [INTEGRATORS_GUIDE.md](INTEGRATORS_GUIDE.md) (`acme` / `animal-care` / `ES`, `_create`, `_create-response`, `_upload`, `_upload-response`)

Documentación operativa:

- Español: [docs/es/README.md](docs/es/README.md)
- Español: [docs/es/13-bootstrap-gcp-onehealth.md](docs/es/13-bootstrap-gcp-onehealth.md)
