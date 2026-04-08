# API config test flow

After starting the service in demo mode, without requiring an exchange token:

```bash
DEMO_MODE=true env PYTHONPATH=src python -m adapter_ingestion.service.main
```

Use this helper in another terminal:

```bash
IAT=$(date +%s)
EXP=$((IAT + 300))
THID="appmypets-$(date +%Y%m%d%H%M%S)"
```

## Upload `AppMyPets-api-config.xlsx`

```bash
IAT=$(date +%s)
EXP=$((IAT + 300))
THID="appmypets-$(date +%Y%m%d%H%M%S)"

curl -sS -X POST \
  "http://127.0.0.1:8080/acme01/cds-es/v1/onehealth-research/digitaltwin/api-config/excel/_upload" \
  -F 'iss=did:web:test.example:employee:loader' \
  -F 'type=https://didcomm.org/plaintext/2.0/message' \
  -F "thid=${THID}" \
  -F "iat=${IAT}" \
  -F "exp=${EXP}" \
  -H "Authorization: Bearer eyJhbGciOiAibm9uZSIsICJ0eXAiOiAiSldUIn0.eyJpc3MiOiAiZGlkOndlYjp0ZXN0LmV4YW1wbGU6ZW1wbG95ZWU6bG9hZGVyIiwgInN1YiI6ICJkaWQ6d2ViOnRlc3QuZXhhbXBsZTplbXBsb3llZTpsb2FkZXIifQ." \
  -F "file=@/Users/fernando/GITS/gdc-workspace/examples/AppMyPets-api-config.xlsx;type=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
```

Polling:

```bash
curl -sS -X POST \
  "http://127.0.0.1:8080/acme01/cds-es/v1/onehealth-research/digitaltwin/api-config/excel/_upload-response?thid=${THID}" \
  -H "content-type: application/didcomm-plain+json" \
  -d "{
    \"iss\":\"did:web:test.example:employee:loader\",
    \"type\":\"https://didcomm.org/plaintext/2.0/message\",
    \"thid\":\"${THID}\",
    \"iat\":${IAT},
    \"exp\":${EXP}
  }"
```

## Upload `Qvet-api-config.xlsx`

```bash
IAT=$(date +%s)
EXP=$((IAT + 300))
THID="qvet-$(date +%Y%m%d%H%M%S)"

curl -sS -X POST \
  "http://127.0.0.1:8080/acme01/cds-es/v1/onehealth-research/digitaltwin/api-config/excel/_upload" \
  -F "iss=did:web:test.example:employee:loader" \
  -F "type=https://didcomm.org/plaintext/2.0/message" \
  -F "thid=${THID}" \
  -F "iat=${IAT}" \
  -F "exp=${EXP}" \
  -F "file=@/Users/fernando/GITS/gdc-workspace/examples/Qvet-api-config.xlsx;type=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

curl -sS -X POST \
  "http://127.0.0.1:8080/acme01/cds-es/v1/onehealth-research/digitaltwin/api-config/excel/_upload-response?thid=${THID}" \
  -H "content-type: application/didcomm-plain+json" \
  -d "{
    \"iss\":\"did:web:test.example:employee:loader\",
    \"type\":\"https://didcomm.org/plaintext/2.0/message\",
    \"thid\":\"${THID}\",
    \"iat\":${IAT},
    \"exp\":${EXP}
  }"
```

## Upload `Wakyma-api-config.xlsx`

```bash
IAT=$(date +%s)
EXP=$((IAT + 300))
THID="wakyma-$(date +%Y%m%d%H%M%S)"

curl -sS -X POST \
  "http://127.0.0.1:8080/acme01/cds-es/v1/onehealth-research/digitaltwin/api-config/excel/_upload" \
  -F "iss=did:web:test.example:employee:loader" \
  -F "type=https://didcomm.org/plaintext/2.0/message" \
  -F "thid=${THID}" \
  -F "iat=${IAT}" \
  -F "exp=${EXP}" \
  -F "file=@/Users/fernando/GITS/gdc-workspace/examples/Wakyma-api-config.xlsx;type=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

curl -sS -X POST \
  "http://127.0.0.1:8080/acme01/cds-es/v1/onehealth-research/digitaltwin/api-config/excel/_upload-response?thid=${THID}" \
  -H "content-type: application/didcomm-plain+json" \
  -d "{
    \"iss\":\"did:web:test.example:employee:loader\",
    \"type\":\"https://didcomm.org/plaintext/2.0/message\",
    \"thid\":\"${THID}\",
    \"iat\":${IAT},
    \"exp\":${EXP}
  }"
```

Important points:

- Use `software_id=api-config` because these spreadsheets contain API-CONFIG rows.
- The correct route for this API is `.../digitaltwin/api-config/excel/_upload`.
- Polling uses `.../_upload-response?thid=...`.

If you also want the converted JSON saved on disk, use the CLI for each file:

```bash
cd /Users/fernando/GITS/gdc-workspace/dataconv-api-py
env PYTHONPATH=src python3.11 -m adapter_ingestion.cli \
  --manufacturer api-config \
  --input /Users/fernando/GITS/gdc-workspace/examples/AppMyPets-api-config.xlsx \
  --issuer-did did:web:test.example:employee:loader \
  --audience-did did:web:test.example \
  --subject-did-prefix did:web:test.example \
  --allow-unmapped-species \
  --dry-run \
  --output-dir ./artifacts
```

This generates:

- `composition-message.json`
- `summary.json`

Repeat the same CLI flow for Qvet and Wakyma by changing only the `--input` path.