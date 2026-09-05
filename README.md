# dataconv-api

Clinical pre-conversion repository with two execution modes:

- `API`: main runtime for integrators and client applications.
- `LEGACY_CLI`: internal/manual validation flow.

This README is the single root entry point in English. Spanish operational material remains available under [docs/es/README.md](docs/es/README.md).

## Start here

Roadmap and briefing:

- [BRIEFING_DATASPACE_EN.md](BRIEFING_DATASPACE_EN.md)
- [TODO_ROADMAP.md](TODO_ROADMAP.md)

Repository documentation:

- Main English docs index: [docs/en/README.md](docs/en/README.md)
- Spanish operational archive: [docs/es/README.md](docs/es/README.md)
- Integrator runbook: [INTEGRATORS_GUIDE.md](INTEGRATORS_GUIDE.md)
- API walkthrough: [docs/en/API_DEVELOPMENT_GUIDE.md](docs/en/API_DEVELOPMENT_GUIDE.md)
- Data space artifacts TODO (Gaia-X): [docs/en/TODO_DATA_SPACE_ARTIFACTS.md](docs/en/TODO_DATA_SPACE_ARTIFACTS.md)
- Accuro API-CONFIG workbook flow: [docs/en/13-accuro-api-config.md](docs/en/13-accuro-api-config.md)

FHIR-like flat claims, physical indexes, and FHIR queries are separate layers:

```text
API-CONFIG:          DiagnosticReport.code-text
resource.meta.claims DiagnosticReport.code-text
database index:      diagnosticreport_code-text
FHIR search:         DiagnosticReport?code:text=diagnóstico
```

DataConv imports the canonical flat claim from `API-CONFIG`, materializes a
`DiagnosticReport`, and translates the FHIR `code:text` modifier only at the
search boundary. The physical index key is internal and preserves the hyphen.
Canonical claim names and normalization helpers come from `gdc-data-utils-py`,
whose catalog is generated from `gdc-common-utils-ts`.

Financial API-CONFIG columns use the same dotted contract. DataConv groups rows
by `Invoice.identifier`, creates one `Invoice` and its separate `ChargeItem`
resources, writes `Invoice.lineItem[].chargeItemReference`, and links every line
back with `ChargeItem.supporting-information`. `ChargeItem.part-of` is never an
invoice link.

The standard financial search subset currently enforced by DataConv is:

- `Invoice`: `date`, `identifier`, `issuer`, `recipient`, `status`, `subject`;
- `ChargeItem`: `code`, `identifier`, `occurrence`, `subject`.

Other financial flat claims can be persisted but are not advertised as HL7 R4
search parameters. Unsupported parameters return HTTP 400 instead of silently
pretending to implement an HL7 search.

Within one resource search, repeated parameters are AND constraints and
comma-separated values are OR alternatives. Multi-resource twin criteria such
as `ChargeItem.code` plus `DiagnosticReport.code-text` belong to the GW CORE
ResearchSubject search boundary and remain pending there; DataConv does not
claim that local per-resource `_search` already proves that gateway behavior.

The legacy Excel `BaseConfig` vocabulary is classified as control fields,
canonical claims, DataConv extensions or pending mappings. Generate a governed
copy without overwriting the source:

```bash
PYTHONPATH=src .venv/bin/python scripts/reconcile-base-config.py \
  "/path/to/mapping.xlsx" "/path/to/mapping-reconciled.xlsx"
```

## 1. Local API setup

Activate a virtual environment before running the API locally.

Recommended local Python version: use `python3.11` so development matches the current Docker deployment runtime. If you run `python3 -m venv`, the virtual environment will inherit whatever interpreter your shell resolves at that moment.

```bash
cd "$HOME"/GITS/gdc-workspace/dataconv-api-py

python3.11 --version
python3.11 -m venv .venv
source .venv/bin/activate

python --version
python -m pip install --upgrade pip
python -m pip install -e ".[api,gcp,postgres,excel,ai]"

cp .env.local.example .env.local
```

If `python3.11` is not in `PATH`, verify the interpreter that your shell resolves before creating `.venv`:

```bash
which python3
python3 --version
```

### Embedded worker mode (`mem`): one terminal

If local execution uses in-memory providers (`mem`), the API starts the embedded worker automatically.

```bash
source .venv/bin/activate
./scripts/run-api-local.sh
```

### Split API and worker mode: two terminals

Use separate terminals when running the API and worker manually outside embedded mode.

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

Important notes:

- If you open a new terminal, run `source .venv/bin/activate` again.
- If you see `preconversion-api: command not found` or `preconversion-worker: command not found`, that terminal does not have `.venv` activated.
- Docker local mode does not require two manual terminals.
- In Kubernetes or other cloud environments, the orchestrator manages API and worker workloads.

Swagger:

- Default URL: `http://127.0.0.1:8080/api-docs`
- Without Docker, use the `LOCAL_PORT` configured in `.env.local`.
- With Docker, use the published host port (`DOCKER_PORT`, by default equal to `LOCAL_PORT`).

## 2. Tests

```bash
source .venv/bin/activate
python -m pip install pytest
python -m pytest -q
```

## 3. Service naming

- Internally, the software still uses `preconvert` in GCP resource names for historical reasons.
- Externally, Docker images, SDKs, and documentation use `dataconv` as the public product name.
- The executable binaries remain `preconversion-api`, `preconversion-worker`, and `preconversion-cleanup`.

## 4. Recommended minimum runtime scope

```bash
# Runtime auth
# true  -> demo or internal mode
# false -> production mode with Bearer tokens from /exchange
DEMO_MODE=true

# CSV of jurisdictions supported by this instance. Use '*' to allow any.
SUPPORTED_JURISDICTIONS=ES

# CSV of sectors supported by this instance. Use '*' to allow any.
SUPPORTED_SECTORS=health-care,animal-care,onehealth-care,onehealth-research,onehealth-insurance
```

Behavior:

- If `SUPPORTED_JURISDICTIONS` does not include the requested jurisdiction, the API returns `404`.
- If `SUPPORTED_SECTORS` does not include the requested sector, the API returns `404`.
- If either variable is `*`, that axis is unrestricted.

Exchange profile note:

- The default `/exchange` flow expects `subject_token` (`id_token`) and standard validations.
- Generic exchange runtime settings such as OIDC, session token, scopes, and insecure assertions remain under `EXCHANGE_*` env names.
- Static/local `api_key` mode is available only when `LOCAL_EXCHANGE_ALLOW_API_KEY=true`.
- Exceptional desktop or non-confidential mode is explicit and disabled by default:
  - set `LOCAL_EXCHANGE_ALLOW_API_KEY_EXCEPTION=true`
  - send `api_key_profile=api-key-exception.v1`
  - send `api_key` (or `X-API-Key`) plus `organization` and preferably `operational_subject`
- Static API key list/defaults for local mode:
  - `LOCAL_EXCHANGE_API_KEYS`
  - `LOCAL_EXCHANGE_API_KEY_SUBJECT_DEFAULT`
  - `LOCAL_EXCHANGE_API_KEY_ORG_DEFAULT`

## 5. Local API and worker against real Google Cloud

If you want to run the local API and worker against real Google Cloud services, using Firestore for vault and PostgreSQL for search:

```bash
cp .env.local.gcp.example .env.local.gcp
source .venv/bin/activate
python -m pip install -e ".[prod]"
```

Complete `.env.local.gcp` with at least:

- `SEARCH_PROVIDER=postgresql`
- `POSTGRES_DSN=...`
- `GCP_PROJECT_ID=...`
- `GCS_BUCKET_NAME=...`

Run locally against real cloud services:

```bash
./scripts/run-api-local-gcp.sh
```

```bash
./scripts/run-worker-local-gcp.sh
```

## 6. Smoke checks and cleanup

Full HTTP smoke test against the local API:

```bash
BASE_URL=http://127.0.0.1:8080 ./scripts/run-integrator-smoke.sh
```

Smoke test for real GCP adapters:

```bash
./scripts/run-gcp-adapter-integration.sh
```

Default public API surface:

- DIDComm contract endpoints only: `_create`, `_create-response`, `_upload`, `_upload-response`
- `healthz`

Global cleanup command for expired jobs:

```bash
source .venv/bin/activate
preconversion-cleanup --dry-run --pretty
```

Operational settings already integrated in the runtime:

- Job response TTL: `PRECONV_JOB_RESULT_TTL_SECONDS`
- Global cleanup cron: `PRECONV_CLEANUP_SCHEDULE`
- Structured JSON lifecycle logs such as `job_created`, `job_response_delivered`, and `job_expired_deleted`

## 7. Docker local, image push, and deployment

### 7.1 Docker local (without `venv`)

```bash
cd "$HOME"/GITS/gdc-workspace/dataconv-api-py
./docker_build_local.sh
```

API:

```bash
./docker_run.sh local
```

Worker:

```bash
PROCESS_MODE=worker ./docker_run.sh local
```

API against real cloud services from Docker:

```bash
./docker_run.sh local-gcp
```

Worker against real cloud services from Docker:

```bash
PROCESS_MODE=worker ./docker_run.sh local-gcp
```

Manual cleanup:

```bash
PROCESS_MODE=cleanup ./docker_run.sh local
```

### 7.2 Publish an image to Artifact Registry manually

```bash
cp .env.deploy.production.example .env.deploy.production
# edit .env.deploy.production with your real values

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

### 7.3 Deploy to GKE

```bash
./cloud_deploy.sh staging
```

Or explicitly:

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

### 7.4 Re-deploy by digest without rebuilding

```bash
PRECONV_IMAGE_REF="europe-west1-docker.pkg.dev/.../vet-claims-api@sha256:..." \
PRECONV_SKIP_BUILD=true \
./scripts/deploy-gke.sh production
```

## 8. Legacy CLI

This flow is not for API integrators. It remains available for internal manual pre-conversion validation.

Base command:

```bash
source .venv/bin/activate
PYTHONPATH=src python -m adapter_ingestion --help
```

## 9. Documentation map

- Integrator runbook: [INTEGRATORS_GUIDE.md](INTEGRATORS_GUIDE.md)
- API walkthrough: [docs/en/API_DEVELOPMENT_GUIDE.md](docs/en/API_DEVELOPMENT_GUIDE.md)
- Operational documentation index: [docs/en/README.md](docs/en/README.md)
- Operating modes: [docs/en/00-operating-modes.md](docs/en/00-operating-modes.md)
- Installation: [docs/en/01-installation.md](docs/en/01-installation.md)
- Run and examples: [docs/en/03-run-and-examples.md](docs/en/03-run-and-examples.md)
- Troubleshooting: [docs/en/05-troubleshooting.md](docs/en/05-troubleshooting.md)
- Quick GKE deployment: [docs/en/10-quick-gke-deployment.md](docs/en/10-quick-gke-deployment.md)
- Release pipeline: [docs/en/11-release-staging-production.md](docs/en/11-release-staging-production.md)
- GCP bootstrap: [docs/en/13-gcp-bootstrap-onehealth.md](docs/en/13-gcp-bootstrap-onehealth.md)
- Spanish operational archive: [docs/es/README.md](docs/es/README.md)
