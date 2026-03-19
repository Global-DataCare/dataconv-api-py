# INTEGRATORS_GUIDE

Guía rápida para integradores que quieran probar la API sin Swagger y guardar requests/responses versionables.

## Objetivo

Este flujo sirve para:

- Probar localmente `API + worker` con `curl`.
- Usar `application/didcomm-plain+json` con `attachments[]`.
- Guardar payloads de entrada y respuestas en `artifacts/integrator-smoke/`.
- Repetir pruebas mucho más rápido que desde Swagger.

## Requisitos

Antes de lanzar el smoke:

```bash
source .venv/bin/activate
preconversion-api
```

En otra terminal:

```bash
source .venv/bin/activate
preconversion-worker
```

## Flujo copy/paste para `acme` (`animal-care`, `ES`)

Ejecuta esto en una tercera terminal:

```bash
cd /Users/fernando/GITS/gdc-workspace/adapter-ingestion-py

BASE_URL="http://127.0.0.1:8080"
ALT="acme"
JUR="ES"
SOFTWARE_ID="qvet-v1.0"
ISS="did:web:clinic.example:employee:it:loader"
DROPBOX_URL="https://www.dropbox.com/scl/fi/gkc57co2y9litpm7t81vt/exampleQvetES.xlsx?rlkey=5cnesxdtop8hfdryhrrlmo89w&st=1rsqrcqp&dl=1"
FILE_PATH="examples/input/exampleQvetES.xlsx"

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

curl -i -sS -X POST "$BASE_URL/host/cds-$JUR/v1/animal-care/$ALT/config/didcomm/_create" \
  -H "Content-Type: application/didcomm-plain+json" \
  --data @/tmp/preconv-acme-create.json | tee /tmp/preconv-acme-create.http

CFG_LOCATION="$(tr -d '\r' < /tmp/preconv-acme-create.http | sed -n 's/^Location: //p' | tail -1)"
CFG_RETURNED_THID="$(printf '%s\n' "$CFG_LOCATION" | sed -n 's/.*[?&]thid=\([^&]*\).*/\1/p')"
echo "CFG_LOCATION=$CFG_LOCATION"
echo "CFG_RETURNED_THID=$CFG_RETURNED_THID"

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

curl -i -sS -X POST "$BASE_URL/$ALT/cds-$JUR/v1/animal-care/conversion/$SOFTWARE_ID/excel/_upload" \
  -H "Content-Type: application/didcomm-plain+json" \
  --data @/tmp/preconv-acme-upload.json | tee /tmp/preconv-acme-upload.http

UP_LOCATION="$(tr -d '\r' < /tmp/preconv-acme-upload.http | sed -n 's/^Location: //p' | tail -1)"
UP_RETURNED_THID="$(printf '%s\n' "$UP_LOCATION" | sed -n 's/.*[?&]thid=\([^&]*\).*/\1/p')"
echo "UP_LOCATION=$UP_LOCATION"
echo "UP_RETURNED_THID=$UP_RETURNED_THID"

curl -sS -X POST "$BASE_URL$UP_LOCATION" \
  -H "Content-Type: application/didcomm-plain+json" \
  -d "{
    \"iss\":\"$ISS\",
    \"type\":\"https://didcomm.org/plaintext/2.0/message\",
    \"iat\":$NOW,
    \"exp\":$EXP
  }" | tee /tmp/preconv-acme-upload-response-1.json
```

Si el último poll devuelve `202`, repítelo hasta obtener `200`:

```bash
curl -sS -X POST "$BASE_URL$UP_LOCATION" \
  -H "Content-Type: application/didcomm-plain+json" \
  -d "{
    \"iss\":\"$ISS\",
    \"type\":\"https://didcomm.org/plaintext/2.0/message\",
    \"iat\":$NOW,
    \"exp\":$EXP
  }" | tee /tmp/preconv-acme-upload-response-final.json
```

Qué debes ver:

- `_create` devuelve `202` con `Location: /host/cds-ES/v1/animal-care/acme/config/didcomm/_create-response?thid=...`
- `_create-response` devuelve un `Bundle` `batch-response` con `body.data[0].response.status = "200"`
- `_upload` devuelve `202` con `Location: /acme/cds-ES/v1/animal-care/conversion/qvet-v1.0/excel/_upload-response?thid=...`
- `_upload-response` termina devolviendo `200` con `body.issues` y `body.data[0].resource`

Importante para local:

- El fichero [examples/input/exampleQvetES.xlsx](/Users/fernando/GITS/gdc-workspace/adapter-ingestion-py/examples/input/exampleQvetES.xlsx) usa `HISTORIA_ID`.
- Si envías un `mappingConfig.fieldMap.subjectId = "ID_HISTORIA"`, el job puede terminar en `succeeded` pero con `body.data[0].resource.body.data = []`, porque todas las filas quedan sin `subjectId`.

## Script de smoke

Script incluido:

- [scripts/run-integrator-smoke.sh](/Users/fernando/GITS/gdc-workspace/adapter-ingestion-py/scripts/run-integrator-smoke.sh)

Ejemplo:

```bash
cd /Users/fernando/GITS/gdc-workspace/adapter-ingestion-py

BASE_URL="http://127.0.0.1:8080" \
ALT="clinic-demo" \
JUR="ES" \
SOFTWARE_ID="qvet-v1.0" \
ISS="did:web:clinic.example:employee:it:loader" \
./scripts/run-integrator-smoke.sh
```

El script:

- envía `_create`
- consulta `_create-response`
- envía `_upload` con DIDComm `attachments[].data.links`
- hace polling de `_upload-response`
- guarda todo en `artifacts/integrator-smoke/requests/<run-id>/` y `artifacts/integrator-smoke/responses/<run-id>/`

URL Dropbox por defecto usada por el script:

- `https://www.dropbox.com/scl/fi/gkc57co2y9litpm7t81vt/exampleQvetES.xlsx?rlkey=5cnesxdtop8hfdryhrrlmo89w&st=1rsqrcqp&dl=1`

Puedes sobrescribirla:

```bash
DROPBOX_URL="https://www.dropbox.com/...&dl=1" ./scripts/run-integrator-smoke.sh
```

## Contrato usado

Swagger en `http://127.0.0.1:8080/api-docs` usa ejemplos cargados desde JSON versionados en `examples/openapi/`.

Helpers de Swagger:

- Si un ejemplo lleva `jti: "req-auto"`, al enviar se sustituye por `req-yyyymmddhhmm`.
- Si un ejemplo lleva `thid: "thid-auto"`, al enviar se sustituye por `thid-yyyymmddhhmm`.
- Las respuestas `202` devuelven `Location` con `?thid=...`, y los endpoints de poll aceptan ese `thid` por query si no lo pones en el body. Esto simplifica mucho el test manual desde Swagger.

Para `_upload` se soportan dos entradas públicas:

- `multipart/form-data` con `file`
- `application/didcomm-plain+json` con top-level `attachments[]`

Forma recomendada para integradores:

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

Notas:

- `attachments[]` va fuera de `body`, como en `dataspace-ica-ts`.
- `body` sigue siendo un mensaje DIDComm plaintext con `body.resourceType = "Bundle"` y `body.data[]`.
- El perfil público actual acepta un solo `attachment` por request y una sola URL en `attachment.data.links`.
- Si llega una URL de Dropbox con `dl=0`, la API intenta normalizarla a `dl=1`.
- Si ves `CERTIFICATE_VERIFY_FAILED` al descargar desde Dropbox, actualiza el entorno con `python -m pip install -e ".[api,excel]"` para instalar `certifi`. Si estás detrás de proxy/CA corporativa, exporta `SSL_CERT_FILE=/ruta/a/ca.pem` antes de arrancar `preconversion-api`.

## Ejemplos de respuesta

Ejemplos versionados:

- [config-create-response.succeeded.sample.json](/Users/fernando/GITS/gdc-workspace/adapter-ingestion-py/examples/integrators/config-create-response.succeeded.sample.json)
- [upload-response.succeeded.sample.json](/Users/fernando/GITS/gdc-workspace/adapter-ingestion-py/examples/integrators/upload-response.succeeded.sample.json)

## Referencias

- [docs/es/API_DEVELOPMENT_GUIDE.md](/Users/fernando/GITS/gdc-workspace/adapter-ingestion-py/docs/es/API_DEVELOPMENT_GUIDE.md)
- [docs/es/08-api-config-multitenant.md](/Users/fernando/GITS/gdc-workspace/adapter-ingestion-py/docs/es/08-api-config-multitenant.md)
