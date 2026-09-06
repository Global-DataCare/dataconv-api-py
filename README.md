# dataconv-api

Clinical pre-conversion repository with two execution modes:

- `API`: main runtime for integrators and client applications.
- `LEGACY_CLI`: internal/manual validation flow.

Organization controllers exchange a fresh signed OIDC token plus the exact
Connect ICA controller VP at
`/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/organization/research/auth/_exchange`.
The short-lived result is limited to `dataconv.upload` and that public legal
`tenant_id`; network, jurisdiction and sector stay separate storage dimensions.

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
API-CONFIG:          coding-input:Condition.code
draft metadata:      meta.codingProposals[]
confirmed claims:    Condition.code + Condition.code-display
FHIR search:         Condition?code=<system>|<code> or Condition?code:text=<English display>
```

DataConv imports diagnosis/pathology text as an unconfirmed coding input,
obtains all governed candidates, and materializes a `Condition` draft without
claiming that source text is an authoritative code. Human review selects one
candidate; only then are `Condition.code` and its English
`Condition.code-display` indexed. The physical index keys remain internal.
Canonical claim names and normalization helpers come from `gdc-data-utils-py`,
whose catalog is generated from `gdc-common-utils-ts`.

## Research review, persistence, and coding-assistance boundary

Every new upload whose sector is explicitly `onehealth-research` carries a literal FHIR Reference object such as
`"researchStudy": {"reference": "ResearchStudy/study-2026-01"}`. DataConv
persists that reference in the job, copies it to the standard
`ResearchSubject.study` flat claim, requires the same reference when polling or
patching the conversion, and requires the standard `study` parameter when
searching ResearchSubject. This is correlation and dataset isolation only:
DataConv does not infer Consent, SMART scope or employee authority from the
reference; those controls remain in GW. Other conversion sectors keep their
existing contract and may omit `researchStudy`.

Firestore jobs created before this field existed can still be polled without
it so an already-running conversion is not lost. That compatibility is
read-only: an unscoped legacy conversion cannot be promoted through `_patch`.
No personal source identifier is copied into the study reference or public
search index.

The persistent research lifecycle is deliberately:

```text
GCS -> Firestore draft -> human review -> PostgreSQL search index
```

- GCS stores the uploaded workbook and generated job artifacts.
- The conversion pipeline produces FHIR-like resources with canonical flat
  claims in `resource.meta.claims`.
- Firestore stores those processed resources as review drafts with
  `userSelected=true`, including the relationships needed to review a complete
  `ResearchSubject`, its `Composition`, and linked resources.
- Human confirmation changes those same processed resources to
  `userSelected=false` and promotes them to PostgreSQL.
- PostgreSQL stores the promoted resource, its exact `claims`, and derived
  `search_fields`. Searches filter `search_fields` and return the stored
  resource in a `Bundle` with `type=searchset`.

Firestore and PostgreSQL do not contain raw versus processed variants: during
promotion PostgreSQL receives a searchable copy of the same processed resource
kept in Firestore. This duplication is a read optimization and must not be
described as two semantic resource versions.

Human review is required because free text may need terminology-code
inference. An AI coding assistant may only propose codes, confidence, and
evidence; it cannot approve or promote a resource. Accepted and rejected
proposals may become a governed, de-identified, human-reviewed evaluation or
training corpus, but must never be collected as automatic ground truth.

The worker uses `NoopCodingAssistant` only when the terminology or coding-model
URL is absent. With both configured it calls the terminology JSON:API, sends
the closed candidate set and allowlisted row context to `/v1/coding/rank`, and
posts explicit human corrections to `/v1/coding/feedback`. Feedback is an
evaluation/training record; it never changes model weights online.

A general model runtime can support separate intent, question-answering, and
clinical-coding adapters, but an intent endpoint must not be reused as if it
were already a terminology API. For coding, DataConv needs a terminology
service constrained by the target system and value set. The standard FHIR R4
building blocks are
[`ValueSet/$expand?filter=`](https://hl7.org/fhir/R4/valueset-operation-expand.html)
for text-filtered candidates,
[`ValueSet/$validate-code`](https://hl7.org/fhir/R4/valueset-operation-validate-code.html)
for membership validation, and
[`ConceptMap/$translate`](https://hl7.org/fhir/R4/conceptmap-operation-translate.html)
for mappings between coding systems. A model may normalize the user's text and
rank the returned candidates, but must not invent the authoritative code.

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

The generated Ingress can optionally expose a terminology Service in the same
namespace without changing the DataConv catch-all route. Set
`PRECONV_TERMINOLOGY_INGRESS_ENABLED=true` together with
`PRECONV_TERMINOLOGY_INGRESS_SERVICE_NAME` and
`PRECONV_TERMINOLOGY_INGRESS_SERVICE_PORT`. Requests under
`/v1/terminology` are forwarded unchanged to that Service; every other path
continues through the DataConv Service at `/`. The terminology Service must
already exist and be compatible with the selected GKE Ingress controller.

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
