# INTEGRATORS_GUIDE

Quick guide for integrators who want to test the API without Swagger and store versionable request and response payloads.

## Goal

This flow is designed to:

- test `API + worker` locally using `curl`
- use `application/didcomm-plain+json` with `attachments[]`
- store input and output payloads under `artifacts/integrator-smoke/`
- iterate faster than with Swagger-only manual testing

## Prerequisites

Before running the smoke flow:

```bash
source .venv/bin/activate
preconversion-api
```

In another terminal:

```bash
source .venv/bin/activate
preconversion-worker
```

## Quick CLI runbook

Recommended flow for demos and CLI screenshots:

- the integrator frontend authenticates the user in Google or Microsoft
- the frontend receives an OIDC `id_token`
- the API validates `id_token` and extracts the user email

### 1) Prepare the CLI environment

```bash
cd $HOME/GITS/gdc-workspace/dataconv-client-sdk-ts

export DATACONV_BASE_URL="http://127.0.0.1:8080"
export DATACONV_TENANT_ID="VATES-A00000001"
export DATACONV_JURISDICTION="ES"
export DATACONV_SECTOR="animal-care"
export DATACONV_SOFTWARE_ID="qvet"
export DATACONV_RESOURCE_TYPE="Composition"
export DATACONV_ID_TOKEN="<REAL_OIDC_ID_TOKEN>"
```

### 2) Local login

```bash
npx tsx src/cli.ts login --id-token "$DATACONV_ID_TOKEN"
```

### 3) Obtain a session token for API key administration

```bash
npx tsx src/cli.ts exchange --scope "dataconv.tenant.keys.manage"
```

### 4) Create a granular API key

```bash
npx tsx src/cli.ts api-key-create \
  --email "operator@integrator.example" \
  --target "publisher/cds-es/v1/animal-care/vates-a00000001/dataset/*/*/_upload" \
  --scope "excel/_upload,DocumentReference/_search,Subject/_search" \
  --instrument '{"permission":[{"action":"update"}]}'
```

### 5) Obtain a session token for uploads

```bash
npx tsx src/cli.ts exchange --scope "dataconv.upload"
```

### 6) Create a mapping before upload

```bash
cat > ./artifacts/mapping-qvet.json <<'JSON'
{
  "mappingConfig": {
    "headerRowIndex": 3,
    "fieldMap": {
      "section": "SECCION",
      "family": "FAMILIA",
      "concept": "CONCEPTO",
      "subject_id": "HISTORIA_ID",
      "date": "FECHA"
    }
  }
}
JSON
```

### 7) Upload and poll

```bash
npx tsx src/cli.ts upload ../examples/exampleQvetES.xlsx \
  --mapping-json ./artifacts/mapping-qvet.json \
  --output-json ./artifacts/appmypets-upload-response-cli.json

npx tsx src/cli.ts whoami
```

Useful notes:

- If `DEMO_MODE=false`, protected operations require a Bearer token from `/exchange`.
- If `exchange` fails on audience or issuer, review `EXCHANGE_OIDC_ALLOWED_ISSUERS` and `EXCHANGE_OIDC_ALLOWED_AUDIENCES`.
- The CLI does not perform Google or Microsoft login; it only consumes an already-issued `id_token`.
- When `--mapping-json` is used, the CLI creates and polls `config/_create-response` before upload.
- The final CLI summary prioritizes `OperationOutcome.issue[0].description` when available.

## Recommended instance scope and auth settings

Configure these variables in `.env.local`:

```bash
DEMO_MODE=true
SUPPORTED_JURISDICTIONS=ES
SUPPORTED_SECTORS=health-care,animal-care,onehealth-care,onehealth-research,onehealth-insurance
```

If the requested jurisdiction or sector is not allowed, the API returns `404`.

## Copy-paste flow for `acme` (`animal-care`, `ES`)

Run this in a third terminal:

```bash
cd $HOME/GITS/gdc-workspace/dataconv-api-py

BASE_URL="http://127.0.0.1:8080"
ALT="acme"
JUR="ES"
SOFTWARE_ID="qvet-v1.0"
ISS="did:web:clinic.example:employee:it:loader"
DROPBOX_URL="https://www.dropbox.com/scl/fi/gkc57co2y9litpm7t81vt/exampleQvetES.xlsx?rlkey=5cnesxdtop8hfdryhrrlmo89w&st=1rsqrcqp&dl=1"

NOW="$(date -u +%s)"
EXP="$((NOW + 3600))"
STAMP="$(date -u +%Y%m%d%H%M)"

CFG_JTI="req-$STAMP"
CFG_THID="thid-$STAMP-cfg"

cat > /tmp/preconv-acme-create.json <<JSON
{
  "iss": "$ISS",
  "thid": "$CFG_THID",
  "jti": "$CFG_JTI",
  "type": "https://didcomm.org/plaintext/2.0/message",
  "iat": $NOW,
  "exp": $EXP,
  "data": [
    {
      "softwareId": "$SOFTWARE_ID"
    }
  ]
}
JSON

curl -i -sS -X POST "$BASE_URL/publisher/cds-$JUR/v1/animal-care/$ALT/$SOFTWARE_ID/config/_create" \
  -H "Content-Type: application/didcomm-plain+json" \
  --data @/tmp/preconv-acme-create.json | tee /tmp/preconv-acme-create.http

CFG_LOCATION="$(tr -d '\r' < /tmp/preconv-acme-create.http | sed -n 's/^Location: //p' | tail -1)"

curl -sS -X POST "$BASE_URL$CFG_LOCATION" \
  -H "Content-Type: application/didcomm-plain+json" \
  -d "{
    \"iss\":\"$ISS\",
    \"type\":\"https://didcomm.org/plaintext/2.0/message\",
    \"iat\":$NOW,
    \"exp\":$EXP
  }" | tee /tmp/preconv-acme-create-response.json

UP_JTI="req-$STAMP-upload"
UP_THID="thid-$STAMP-upload"

cat > /tmp/preconv-acme-upload.json <<JSON
{
  "iss": "$ISS",
  "thid": "$UP_THID",
  "jti": "$UP_JTI",
  "type": "https://didcomm.org/plaintext/2.0/message",
  "iat": $NOW,
  "exp": $EXP,
  "body": {
    "resourceType": "Bundle",
    "type": "batch",
    "data": [],
    "total": 0
  },
  "attachments": [
    {
      "id": "source-xlsx",
      "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "filename": "exampleQvetES.xlsx",
      "data": {
        "links": [
          "$DROPBOX_URL"
        ]
      }
    }
  ]
}
JSON

curl -i -sS -X POST "$BASE_URL/publisher/cds-$JUR/v1/animal-care/$ALT/dataset/$SOFTWARE_ID/excel/_upload" \
  -H "Content-Type: application/didcomm-plain+json" \
  --data @/tmp/preconv-acme-upload.json | tee /tmp/preconv-acme-upload.http

UP_LOCATION="$(tr -d '\r' < /tmp/preconv-acme-upload.http | sed -n 's/^Location: //p' | tail -1)"

curl -sS -X POST "$BASE_URL$UP_LOCATION" \
  -H "Content-Type: application/didcomm-plain+json" \
  -d "{
    \"iss\":\"$ISS\",
    \"type\":\"https://didcomm.org/plaintext/2.0/message\",
    \"iat\":$NOW,
    \"exp\":$EXP
  }" | tee /tmp/preconv-acme-upload-response-1.json
```

If the last poll returns `202`, repeat it until you receive `200`.

Expected outcome:

- `_create` returns `202` with a `Location` header pointing to `_create-response`
- `_create-response` returns a `batch-response` bundle with `body.data[0].response.status = "200"`
- `_upload` returns `202` with a `Location` header pointing to `_upload-response`
- `_upload-response` eventually returns `200` with `body.issues` and `body.data[0].resource`

Important local detail:

- `../examples/exampleQvetES.xlsx` uses `HISTORIA_ID`
- if `mappingConfig.fieldMap.subjectId` is set to `ID_HISTORIA`, the job can finish successfully but return an empty conversion payload because every row is missing `subjectId`

## Smoke script

Included script:

- `scripts/run-integrator-smoke.sh`

Example:

```bash
cd $HOME/GITS/gdc-workspace/dataconv-api-py

BASE_URL="http://127.0.0.1:8080" \
ALT="clinic-demo" \
JUR="ES" \
SOFTWARE_ID="qvet-v1.0" \
ISS="did:web:clinic.example:employee:it:loader" \
./scripts/run-integrator-smoke.sh
```

The script:

- sends `_create`
- polls `_create-response`
- sends `_upload` using DIDComm `attachments[].data.links`
- polls `_upload-response`
- stores all requests and responses under `artifacts/integrator-smoke/`

## Public contract summary

Swagger at `http://127.0.0.1:8080/api-docs` loads versioned examples from `examples/openapi/`.

For `_upload`, the supported public inputs are:

- `multipart/form-data` with `file`
- `application/didcomm-plain+json` with top-level `attachments[]`

Recommended payload shape:

```json
{
  "iss": "did:web:clinic.example:employee:it:loader",
  "thid": "up-123",
  "jti": "up-123",
  "type": "https://didcomm.org/plaintext/2.0/message",
  "iat": 1760000000,
  "exp": 1760003600,
  "body": {
    "resourceType": "Bundle",
    "type": "batch",
    "data": [],
    "total": 0
  },
  "attachments": [
    {
      "id": "source-xlsx",
      "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "filename": "exampleQvetES.xlsx",
      "data": {
        "links": [
          "https://www.dropbox.com/...&dl=1"
        ]
      }
    }
  ]
}
```

Notes:

- `attachments[]` stays outside `body`
- one attachment and one URL are supported today
- the API attempts to normalize Dropbox links from `dl=0` to `dl=1`
- if Dropbox downloads fail with `CERTIFICATE_VERIFY_FAILED`, install `certifi` through `python -m pip install -e ".[api,excel]"` or export `SSL_CERT_FILE` to a valid corporate CA bundle

## Sample responses

- `examples/integrators/config-create-response.succeeded.sample.json`
- `examples/integrators/upload-response.succeeded.sample.json`

## References

- [docs/en/API_DEVELOPMENT_GUIDE.md](docs/en/API_DEVELOPMENT_GUIDE.md)
- [docs/en/08-multi-tenant-api-configuration.md](docs/en/08-multi-tenant-api-configuration.md)
