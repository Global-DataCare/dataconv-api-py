# API_DEVELOPMENT_GUIDE

Guía para probar la API en local de extremo a extremo usando:

- `../examples/exampleQvetES.xlsx`

## 1) Preparar entorno local

```bash
cd $HOME/GITS/gdc-workspace/dataconv-api-py
source .venv/bin/activate
python -m pip install -e ".[api,excel]"
cp .env.local.example .env.local
```

Arrancar en terminales separadas:

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

## 2) Variables de prueba

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

## 3) 1.1 Request Creation of Tenant Configuration (`_create`)

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
    }]\
  }"
```

Respuesta esperada:

- HTTP `202 Accepted`
- Headers `Location` y `Retry-After`
- Sin body (el resultado funcional se consulta en `_create-response`)

`mappingConfig` (claves activas):

- `headerRowIndex`, `fieldMap`, `fieldDefaults`
- `speciesContains`
- `allowedSections`, `excludedSections`, `excludedSectionFamilies`
- `ownerPublicRules`
- `loincBySectionFamily`
- `encounterClassBySectionFamily`, `encounterServiceTypeBySectionFamily`

## 4) 1.2 Retrieve Response for Tenant Configuration (`_create-response`)

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

Nota: `_create-response` tiene semántica POP (se consume una sola vez).

Nota para Swagger:

- Los ejemplos publicados en `api-docs` se cargan desde `examples/openapi/*.json`.
- Si envías el ejemplo con `jti: "req-auto"` o `thid: "thid-auto"`, Swagger sustituye esos valores automáticamente por un sufijo UTC `yyyymmddhhmm`.
- La cabecera `Location` ya incluye `?thid=...`, y `_create-response` acepta ese `thid` por query como ayuda para test manual.

Respuesta esperada en `_create-response`:

- Mensaje DIDComm-like con `body.resourceType = "Bundle"` y `body.type = "batch-response"`.
- `body.issues` (OperationOutcome) resume el resultado global del batch (estilo Bundle R5).
- Cada `body.data[]` entry trae:
  - `resource` con objeto persistido canónico (`id`, `type`, `content`, `revision`, `createdAt`, `updatedAt`, `audit`).
  - `response.status` (por ejemplo `200`, `400`, `401`, `500`).
  - `response.outcome` (`OperationOutcome`) con el diagnóstico.
- En entradas con error de configuración, `resource` también está presente (preview de la entrada) para correlacionar el `OperationOutcome` con esa configuración concreta.

## 5) 2.1 Conversion Upload Request (`_upload`)

Opción A: `multipart/form-data` (sigue soportada)

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

Opción B: `application/didcomm-plain+json` con `attachments[]` (más cómodo desde Swagger)

Nota:

- Para Dropbox compartido, usa URL directa con `dl=1`.
- Si pegas `dl=0`, la API intenta normalizarlo a `dl=1` antes de descargar.

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

Debes recibir `202` con cabeceras:

- `Location: .../_upload-response?thid=...`
- `Retry-After: ...`

## 6) 2.2 Retrieve Response for Conversion (`_upload-response`)

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

También se puede usar el `thid` devuelto en `Location`:

```bash
curl -sS -X POST "$BASE_URL/publisher/cds-$JUR/v1/animal-care/$ALT/dataset/$SOFTWARE_ID/excel/_upload-response?thid=$UP_THID" \
  -H "Content-Type: application/didcomm-plain+json" \
  -d "{\
    \"iss\":\"$ISS\",\
    \"type\":\"https://didcomm.org/plaintext/2.0/message\",\
    \"iat\":$NOW,\
    \"exp\":$EXP\
  }"
```

Estados esperados:

- `queued` o `running` -> devuelve un `Bundle` `batch-response` con `body.issues` y `body.data[0].response.status = "202"`.
- `succeeded` -> devuelve un `Bundle` `batch-response`; `body.data[0]` representa el input procesado y `body.data[0].resource` contiene el output convertido (otro `Bundle`).
- si faltan mapeos `section:family -> LOINC`, esas filas se omiten.
- por cada fila omitida se añade un recurso `OperationOutcome` dentro del `Bundle` convertido (`body.data[0].resource.data[]`).
- ese detalle agregado se informa en `body.issues.issue[].diagnostics` y en `body.data[0].response.outcome.issue[].diagnostics`.
- `failed` -> revisar `body.issues.issue[].diagnostics` y `body.data[0].response.outcome.issue[].diagnostics`.

## 7) Limpieza y logs

Limpiar jobs expirados (global, todos los tenants):

```bash
source .venv/bin/activate
preconversion-cleanup --dry-run --pretty
```

Eventos de lifecycle para depuración (stdout/Cloud Logging):

- `job_created`
- `job_processing_started`
- `job_processing_succeeded`
- `job_processing_failed`
- `job_response_delivered`
- `job_expired_deleted`
- `job_cleanup_*`

## 8) Si usas auth estricta

Contrato V2: endpoints de negocio usan `Authorization: Bearer <access_token>`.
`id_token` se usa en el flujo de identidad/exchange, no en payload DIDComm de negocio.
Si `DEMO_MODE=false`, el Bearer emitido por `/exchange` es obligatorio y validado.
Si `DEMO_MODE=true`, se mantiene compatibilidad temporal para clientes legacy, pero en Swagger/documentación se recomienda usar Bearer también.

Referencia completa de contrato:

- [08 - Configuración multi-tenant para API](08-api-config-multitenant.md)
