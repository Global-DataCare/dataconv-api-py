
Tras arrancar el servicio en modo demo (sin requerir token de exchange)

DEMO_MODE=true env PYTHONPATH=src python -m adapter_ingestion.service.main

Usa este helper en otra terminal:

```bash
IAT=$(date +%s)
EXP=$((IAT + 300))
THID="appmypets-$(date +%Y%m%d%H%M%S)"
```

Upload de AppMyPets-api-config.xlsx:

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
Para Qvet-api-config.xlsx:

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
Para Wakyma-api-config.xlsx:

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

Puntos importantes:

uso software_id=api-config porque esos ficheros llevan filas API-CONFIG
el path correcto para esta API es .../digitaltwin/api-config/excel/_upload
el polling va a .../_upload-response?thid=...

Si quieres ver también el JSON convertido en disco, para cada fichero puedes usar además el CLI:

```bash
cd /Users/fernando/GITS/gdc-workspace/dataconv-api-py
env PYTHONPATH=src python3 -m adapter_ingestion.cli \
  --manufacturer api-config \
  --input /Users/fernando/GITS/gdc-workspace/examples/AppMyPets-api-config.xlsx \
  --issuer-did did:web:test.example:employee:loader \
  --audience-did did:web:test.example \
  --subject-did-prefix did:web:test.example \
  --allow-unmapped-species \
  --dry-run \
  --output-dir ./artifacts
```

Eso te deja:

composition-message.json
summary.json
Y lo mismo para Qvet/Wakyma, cambiando el --input.