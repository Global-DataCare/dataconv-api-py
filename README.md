# dataconv-api

Language:

- Español: [README_es.md](README_es.md)
- English: pending (`README_en.md`)

## Inicio rápido local (API + worker)

Preparación:

```bash
cd dataconv-api-py

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e ".[api,gcp,postgres,excel,ai]"

cp env.local.example .env.local
```

Para ejecutar los tests:
```bash
$ source .venv/bin/activate && pip install pytest && pytest
```

### Modo local `mem` (worker embebido): 1 terminal

Si ejecutas en local con providers en memoria (`mem`), la API levanta worker embebido automáticamente y basta un solo proceso:

```bash
source .venv/bin/activate
./scripts/run-api-local.sh
```

### Modo no embebido (`gcloud`): 2 terminales (solo ejecución manual local)

Importante: si abres una terminal nueva, debes volver a ejecutar `source .venv/bin/activate` en esa terminal.

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

- Esto aplica a ejecución local manual sin worker embebido (`mem`).
- En Docker local no necesitas dos terminales manuales para API/worker.
- En Kubernetes/cloud, API y worker se ejecutan como workloads gestionados por el orquestador.

Swagger local:

- URL por defecto: `http://127.0.0.1:8080/api-docs`
- Si ejecutas sin Docker, usa el `LOCAL_PORT` configurado en tu `.env.local`.
- Si ejecutas con Docker, usa el puerto publicado en host (`DOCKER_PORT`, por defecto igual a `LOCAL_PORT`).

**Note on service naming:**

- Internally, the software uses **"preconvert"** as a prefix in GCP resources (Firestore, PubSub, GCS) for historical reasons.
- Externally (Docker, SDK, documentation), we use **"dataconv"** as the public product name.
- The executable binary is called `preconversion-api`, but it's the same thing — both names refer to the same software.

## Configuración mínima recomendada (auth + alcance)

Variables de entorno:

```bash
# Auth runtime
# true  -> demo/interno (no exige Bearer de /exchange)
# false -> producción (exige Bearer emitido por /exchange)
DEMO_MODE=true

# CSV de jurisdicciones soportadas por esta instancia.
# Usa '*' para permitir cualquiera.
SUPPORTED_JURISDICTIONS=ES

# CSV de sectores soportados por esta instancia.
# Usa '*' para permitir cualquiera.
SUPPORTED_SECTORS=health-care,animal-care,onehealth-care,onehealth-research,onehealth-insurance
```

Comportamiento:

- Si `SUPPORTED_JURISDICTIONS` no contiene la jurisdicción pedida, la API responde `404`.
- Si `SUPPORTED_SECTORS` no contiene el sector pedido, la API responde `404`.
- Si cualquiera de ambas variables es `*`, no se restringe ese eje.

Más detalle:

- Español: [INTEGRATORS_GUIDE.md](INTEGRATORS_GUIDE.md)
- Español: [README_es.md](README_es.md)
- Español: [docs/es/API_DEVELOPMENT_GUIDE.md](docs/es/API_DEVELOPMENT_GUIDE.md)

Flujo copy/paste recomendado para integradores:

- [INTEGRATORS_GUIDE.md](INTEGRATORS_GUIDE.md) (`acme` / `animal-care` / `ES`, `_create`, `_create-response`, `_upload`, `_upload-response`)

Documentación operativa:

- Español: [docs/es/README.md](docs/es/README.md)
- Español: [docs/es/13-bootstrap-gcp-onehealth.md](docs/es/13-bootstrap-gcp-onehealth.md)
