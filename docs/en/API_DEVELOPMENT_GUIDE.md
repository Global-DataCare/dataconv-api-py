# API_DEVELOPMENT_GUIDE

End-to-end guide to test the local API using:

- `../examples/exampleQvetES.xlsx`

## 1) Prepare the local environment

```bash
cd /Users/fernando/GITS/gdc-workspace/dataconv-api-py
source .venv/bin/activate
python -m pip install -e ".[api,excel]"
cp .env.local.example .env.local
```

Start the processes in separate terminals:

```bash
source .venv/bin/activate
preconversion-api
```

```bash
source .venv/bin/activate
preconversion-worker
```

Swagger:

- `http://127.0.0.1:8080/api-docs`

## 2) Test variables

```bash
BASE_URL="http://127.0.0.1:8080"
ALT="clinic-demo"
JUR="ES"
SOFTWARE_ID="qvet-v1.0"
ISS="did:web:clinic.example:employee:it:loader"

NOW="$(date +%s)"
EXP="$((NOW + 300))"
CFG_THID="cfg-$(uuidgen)"
UP_THID="up-$(uuidgen)"
```

## 3) Create tenant configuration (`_create`)

```bash
curl -sS -X POST "$BASE_URL/publisher/cds-$JUR/v1/animal-care/$ALT/$SOFTWARE_ID/config/_create" \
  -H "Content-Type: application/didcomm-plain+json" \
  -d "{\
    \"iss\":\"$ISS\",\
    \"thid\":\"$CFG_THID\",\
    \"jti\":\"$CFG_THID\",\
    \"type\":\"https://didcomm.org/plaintext/2.0/message\",\
    \"iat\":$NOW,\
    \"exp\":$EXP,\
    \"data\":[{\
      \"softwareId\":\"$SOFTWARE_ID\",\
      \"config\":{\
        \"mappingConfig\":{\
          \"headerRowIndex\":1,\
          \"fieldMap\":{\
            \"section\":\"SECCION\",\
            \"family\":\"FAMILIA\",\
            \"subfamily\":\"SUBFAMILIA\",\
            \"concept\":\"CONCEPTO\",\
            \"subjectId\":\"HISTORIA_ID\",\
            \"species\":\"ESPECIE\",\
            \"sourceId\":\"IDARTICULO\",\
            \"date\":\"FECHA\",\
            \"time\":\"HORA\"\
          }\
        }\
      }\
    }]}"
```

Expected response:

- HTTP `202 Accepted`
- `Location` and `Retry-After` headers
- no functional body

Active `mappingConfig` keys include `headerRowIndex`, `fieldMap`, `fieldDefaults`, `speciesContains`, `allowedSections`, `excludedSections`, `excludedSectionFamilies`, `ownerPublicRules`, `loincBySectionFamily`, `encounterClassBySectionFamily`, and `encounterServiceTypeBySectionFamily`.

## 4) Poll `_create-response`

```bash
curl -sS -X POST "$BASE_URL/publisher/cds-$JUR/v1/animal-care/$ALT/$SOFTWARE_ID/config/_create-response" \
  -H "Content-Type: application/didcomm-plain+json" \
  -d "{\
    \"iss\":\"$ISS\",\
    \"thid\":\"$CFG_THID\",\
    \"type\":\"https://didcomm.org/plaintext/2.0/message\",\
    \"iat\":$NOW,\
    \"exp\":$EXP\
  }"
```

Notes:

- `_create-response` has POP semantics and is consumed once.
- Swagger examples in `api-docs` are loaded from `examples/openapi/*.json`.
- Auto placeholders such as `req-auto` and `thid-auto` are replaced with UTC suffixes.

## 5) Upload conversion input (`_upload`)

Multipart option:

```bash
curl -i -sS -X POST "$BASE_URL/publisher/cds-$JUR/v1/animal-care/$ALT/dataset/$SOFTWARE_ID/excel/_upload" \
  -F "file=@../examples/exampleQvetES.xlsx" \
  -F "iss=$ISS" \
  -F "thid=$UP_THID" \
  -F "jti=$UP_THID" \
  -F "type=https://didcomm.org/plaintext/2.0/message" \
  -F "iat=$NOW" \
  -F "exp=$EXP"
```

DIDComm option with `attachments[]`:

```bash
curl -i -sS -X POST "$BASE_URL/publisher/cds-$JUR/v1/animal-care/$ALT/dataset/$SOFTWARE_ID/excel/_upload" \
  -H "Content-Type: application/didcomm-plain+json" \
  -d "{\
    \"iss\":\"$ISS\",\
    \"thid\":\"$UP_THID\",\
    \"jti\":\"$UP_THID\",\
    \"type\":\"https://didcomm.org/plaintext/2.0/message\",\
    \"iat\":$NOW,\
    \"exp\":$EXP,\
    \"body\":{\
      \"resourceType\":\"Bundle\",\
      \"type\":\"batch\",\
      \"data\":[],\
      \"total\":0\
    },\
    \"attachments\":[{\
      \"id\":\"source-xlsx\",\
      \"media_type\":\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\",\
      \"filename\":\"exampleQvetES.xlsx\",\
      \"data\":{\
        \"links\":[\"https://www.dropbox.com/s/example123/exampleQvetES.xlsx?dl=1\"]\
      }\
    }]\
  }"
```

Expected response:

- HTTP `202`
- `Location: .../_upload-response?thid=...`
- `Retry-After`

## 6) Poll `_upload-response`

```bash
curl -sS -X POST "$BASE_URL/publisher/cds-$JUR/v1/animal-care/$ALT/dataset/$SOFTWARE_ID/excel/_upload-response" \
  -H "Content-Type: application/didcomm-plain+json" \
  -d "{\
    \"iss\":\"$ISS\",\
    \"thid\":\"$UP_THID\",\
    \"type\":\"https://didcomm.org/plaintext/2.0/message\",\
    \"iat\":$NOW,\
    \"exp\":$EXP\
  }"
```

You can also use the `thid` returned in `Location`.

Expected states:

- `queued` or `running`: response `202` in a `Bundle` `batch-response`
- `succeeded`: response `200` with the converted output bundle in `body.data[0].resource`
- `failed`: inspect `body.issues.issue[].diagnostics` and `body.data[0].response.outcome.issue[].diagnostics`

When `section:family -> LOINC` mappings are missing, those rows are skipped and represented as `OperationOutcome` resources inside the converted bundle.

## 7) Cleanup and logs

```bash
source .venv/bin/activate
preconversion-cleanup --dry-run --pretty
```

Lifecycle events emitted to stdout or Cloud Logging include:

- `job_created`
- `job_processing_started`
- `job_processing_succeeded`
- `job_processing_failed`
- `job_response_delivered`
- `job_expired_deleted`
- `job_cleanup_*`

## 8) Strict auth mode

The V2 contract uses `Authorization: Bearer <access_token>` for business endpoints.

- `id_token` belongs to identity and exchange, not to DIDComm business payloads.
- If `DEMO_MODE=false`, Bearer tokens from `/exchange` are mandatory.
- If `DEMO_MODE=true`, legacy compatibility remains temporarily available, but Bearer is still the recommended path.
- Generic exchange runtime settings such as OIDC, session token, scopes, and insecure assertions remain under `EXCHANGE_*` env names.
- API key exchange is controlled:
  - `LOCAL_EXCHANGE_ALLOW_API_KEY=true` enables local static API key mode.
  - `LOCAL_EXCHANGE_ALLOW_API_KEY_EXCEPTION=true` enables explicit exceptional profile `api_key_profile=api-key-exception.v1` for non-confidential desktop clients.

Full reference:

- [08 - Multi-tenant API configuration](08-multi-tenant-api-configuration.md)
