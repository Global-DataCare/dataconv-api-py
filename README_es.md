# adapter-ingestion-py

Repositorio de pre-conversión clínica con dos modos:

- `API` (modo principal para integradores y clientes).
- `LEGACY_CLI` (solo pruebas internas/manuales).

## 1) API local (recomendado, 2 terminales)

Sí: para ejecutar la API en local debes activar el entorno virtual antes.

```bash
cd /Users/fernando/GITS/gdc-workspace/dataconv-api-py

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e ".[api,excel]"

cp .env.local.example .env.local
```

Arranque en terminales separadas:

Importante:

- Si abres una terminal nueva, debes volver a ejecutar `source .venv/bin/activate`.
- Si ves `preconversion-api: command not found` o `preconversion-worker: command not found`, la terminal no tiene `.venv` activado.

```bash
./scripts/run-api-local.sh
```

```bash
./scripts/run-worker-local.sh
```

Swagger local:

- `http://127.0.0.1:8080/api-docs`

Si quieres levantar API + worker locales contra Google Cloud real, con Firestore para vault y PostgreSQL para search:

```bash
cp .env.local.gcp.example .env.local.gcp
source .venv/bin/activate
python -m pip install -e ".[prod]"
```

Completa en `.env.local.gcp`:

- `SEARCH_PROVIDER=postgresql`
- `POSTGRES_DSN=...`
- `GCP_PROJECT_ID=...`
- `GCS_BUCKET_NAME=...`

Arranque local contra cloud real:

```bash
./scripts/run-api-local-gcp.sh
```

```bash
./scripts/run-worker-local-gcp.sh
```

Smoke HTTP completo contra la API local:

```bash
BASE_URL=http://127.0.0.1:8080 ./scripts/run-integrator-smoke.sh
```

Smoke de adapters GCP reales:

```bash
./scripts/run-gcp-adapter-integration.sh
```

Superficie API pública por defecto:

- Solo endpoints DIDComm de contrato (`_create`, `_create-response`, `_upload`, `_upload-response`) + `healthz`.

Comando de limpieza global de jobs expirados:

```bash
source .venv/bin/activate
preconversion-cleanup --dry-run --pretty
```

## 2) Guía de uso de API con fichero real

Se copió el ejemplo a:

- `examples/input/exampleQvetES.xlsx`

Guía paso a paso (create, create-response, upload, upload-response):

- [API_DEVELOPMENT_GUIDE](docs/es/API_DEVELOPMENT_GUIDE.md)
- [INTEGRATORS_GUIDE](INTEGRATORS_GUIDE.md)

Flujo copy/paste listo para integradores (`acme`, `animal-care`, `ES`):

- [INTEGRATORS_GUIDE](INTEGRATORS_GUIDE.md)

## 3) Docker local + push + deploy (end-to-end)

### 3.1 Docker local (sin `venv`)

```bash
cd /Users/fernando/GITS/gdc-workspace/dataconv-api-py
./docker_build_local.sh
```

API (terminal 1):

```bash
./docker_run.sh local
```

Worker (terminal 2):

```bash
PROCESS_MODE=worker ./docker_run.sh local
```

API contra cloud real desde Docker:

```bash
./docker_run.sh local-gcp
```

Worker contra cloud real desde Docker:

```bash
PROCESS_MODE=worker ./docker_run.sh local-gcp
```

Cleanup manual:

```bash
PROCESS_MODE=cleanup ./docker_run.sh local
```

Swagger local:

- `http://127.0.0.1:8080/api-docs`

### 3.2 Publicar imagen en Artifact Registry (manual)

```bash
cp .env.deploy.production.example .env.deploy.production
# editar .env.deploy.production con tus valores reales

set -a
source .env.deploy.production
set +a

gcloud auth login
gcloud config set project "$GCP_PROJECT_ID"
gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev" -q

gcloud artifacts repositories describe "$ARTIFACT_REGISTRY_REPO" --location "$GCP_REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$ARTIFACT_REGISTRY_REPO" \
    --repository-format=docker \
    --location="$GCP_REGION" \
    --description="Preconversion images"

IMAGE_URI="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY_REPO}/${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG}"
docker build -t "$IMAGE_URI" .
docker push "$IMAGE_URI"
docker image inspect --format='{{index .RepoDigests 0}}' "$IMAGE_URI"
```

### 3.3 Desplegar en GKE (automático con script)

```bash
./cloud_deploy.sh staging
```

o explícitamente:

```bash
./scripts/deploy-gke.sh staging

set -a
source .env.deploy.staging
set +a

kubectl -n "$K8S_NAMESPACE" get deploy
kubectl -n "$K8S_NAMESPACE" get pods -o wide
kubectl -n "$K8S_NAMESPACE" get svc
kubectl -n "$K8S_NAMESPACE" get ingress
```

### 3.4 Re-desplegar por digest (sin recompilar)

```bash
PRECONV_IMAGE_REF="europe-west1-docker.pkg.dev/.../vet-claims-api@sha256:..." \
PRECONV_SKIP_BUILD=true \
./scripts/deploy-gke.sh production
```

Referencia completa:

- [10 - Despliegue rápido en GKE](docs/es/10-despliegue-gke.md)
- [11 - Release staging a production](docs/es/11-release-staging-production.md)
- [13 - Bootstrap GCP onehealth](docs/es/13-bootstrap-gcp-onehealth.md)

Notas operativas ya integradas:

- TTL de respuesta de jobs: `PRECONV_JOB_RESULT_TTL_SECONDS`.
- Cron de limpieza global: `PRECONV_CLEANUP_SCHEDULE`.
- Logs estructurados JSON para lifecycle de jobs (`job_created`, `job_response_delivered`, `job_expired_deleted`, etc.).

## 4) LEGACY_CLI (solo pruebas internas)

Este flujo no es el de integradores API. Se mantiene para validaciones manuales de preconversión.

Comando base:

```bash
source .venv/bin/activate
PYTHONPATH=src python -m adapter_ingestion --help
```

Referencia:

- [00 - Modos de operación](docs/es/00-modos-operacion.md)
- [03 - Ejecución y ejemplos](docs/es/03-ejecucion-ejemplos.md)
- [06 - Script rápido para IT](docs/es/06-script-rapido.md)

## 5) Índice documentación

- [docs/es/README.md](docs/es/README.md)
