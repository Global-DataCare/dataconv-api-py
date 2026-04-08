# 08 - Multi-Tenant API Configuration

Goal: reuse the current adapter behind an API while preserving clinic-specific configuration with a clear DIDComm and FAPI contract for integrators.

This document assumes an iClaims API per vertical and locale, for example `vet-claims-api`.

## 1) Tenant configuration contract

Store one configuration document per `(tenantDid, softwareId)`.

Rules:

- `softwareId` is the public identifier, for example `qvet-v1.0`.
- Internally the runtime splits that into `manufacturer=qvet` and `manufacturerVersion=v1.0`.

Reference payload:

- `configs/tenant-adapter-config.api.example.json`

Key fields:

- `config.mappingConfig`: columns, filters, and `loincBySectionFamily`
- `config.mappingConfig.excludedSectionFamilies`: optional deny-list by `section:family`
- `config.speciesFhir`: optional advanced override for the server-side FHIR species catalog
- `config.speciesLocalToFhirCode`: local text to FHIR code mapping
- `config.runtimeDefaults`: execution defaults such as language, `dataUse`, and `subjectKind`

Active `mappingConfig` keys:

- `headerRowIndex`
- `fieldMap`
- `fieldDefaults`
- `speciesContains`
- `allowedSections`
- `excludedSections`
- `excludedSectionFamilies`
- `ownerPublicRules`
- `loincBySectionFamily`
- `encounterClassBySectionFamily`
- `encounterServiceTypeBySectionFamily`

Notes:

- `patientRules` is legacy and not part of the recommended contract.
- Unsupported extra keys are stored today but ignored by the runtime.
- `sourceId` is optional. If omitted, the adapter generates a stable row identifier.

## 2) Versioning rules

Recommended public key:

- `(tenantDid, softwareId)`

Persist metadata such as:

- `updatedAt`
- `revision`
- `audit.updatedBy`

Do not overwrite records without optimistic locking by `revision`.

## 3) Implemented endpoints

1. `POST /publisher/cds-{jurisdiction}/v1/animal-care/{alternate-name}/{software-id}/config/_create`
2. `POST /publisher/cds-{jurisdiction}/v1/animal-care/{alternate-name}/{software-id}/config/_create-response`
3. `POST /publisher/cds-{jurisdiction}/v1/animal-care/{alternate-name}/dataset/{software-id}/{csv|excel}/_upload`
4. `POST /publisher/cds-{jurisdiction}/v1/animal-care/{alternate-name}/dataset/{software-id}/{csv|excel}/_upload-response`

Behavior summary:

- `_create` returns `202` with `Location` and `Retry-After`, without a functional body.
- `_create-response` returns a DIDComm-like `Bundle` of type `batch-response`.
- Each `body.data[]` entry includes `response.status`, `response.outcome`, and the persisted `resource` preview.
- `_create-response` is single-consumption POP semantics.
- `_upload` returns `202` with `Location` and `Retry-After`.
- `_upload-response` returns `202` while the job is queued or running, and `200` on terminal success or failure.
- Terminal `_upload-response` payloads expire according to `PRECONV_JOB_RESULT_TTL_SECONDS`.
- Public contract errors are exposed as `OperationOutcome` with `400`, `401`, `403`, `404`, or `500`.

Runtime and logging notes:

- Missing `section:family -> LOINC` mappings cause those rows to be omitted.
- Every omitted row generates an `OperationOutcome` inside the converted bundle.
- Lifecycle events are emitted in structured logs such as `job_created`, `job_response_delivered`, and `job_cleanup_*`.

## 4) Automatic bootstrap on upload

If `_upload` receives no existing configuration for the selector, the API generates a base configuration automatically with:

- standard `fieldMap` for `SECTION/FAMILY/SUBFAMILY/CONCEPT/SUBJECT_ID/SPECIES/DATE/TIME`
- `speciesFhir` loaded from `PRECONV_DEFAULT_SPECIES_FHIR_FILE`
- empty `speciesLocalToFhirCode`
- optional `runtimeDefaults.language` derived from jurisdiction
- optional `runtimeDefaults.dataUse`, defaulting to `secondary`

## 5) Public input formats for `_upload`

Recommended public formats:

- `multipart/form-data` with `file`
- `application/didcomm-plain+json` with top-level `attachments[]`

Envelope rules:

- `iss`, `type`, `thid`, `iat`, and `exp` are mandatory
- `jti` is optional but recommended for anti-replay and message tracking
- `requestedBy` is not part of the public contract; the server derives it from `iss`
- `facilityId` is reserved for future use and ignored today
- `attachments[].data` accepts inline `base64` or external `links[]`
- Only one attachment and one link are supported per upload request today
- `Content-Encoding: gzip` is supported at the HTTP layer
- The business contract remains `POST` only

## 6) Minimal upload examples

Multipart upload:

```bash
curl -X POST "https://<host>/publisher/cds-ES/v1/animal-care/<alternate-name>/dataset/qvet-v1.0/excel/_upload" \
  -F "file=@/path/export.xlsx" \
  -F "iss=did:web:clinic.example:employee:it:loader" \
  -F "type=https://didcomm.org/plaintext/2.0/message" \
  -F "thid=<uuid>" \
  -F "jti=<uuid>" \
  -F "iat=1760000000" \
  -F "exp=1760003600"
```

DIDComm upload with `attachments[]`:

```bash
curl -X POST "https://<host>/publisher/cds-ES/v1/animal-care/<alternate-name>/dataset/qvet-v1.0/excel/_upload" \
  -H "Content-Type: application/didcomm-plain+json" \
  -d '{
    "iss": "did:web:clinic.example:employee:it:loader",
    "type": "https://didcomm.org/plaintext/2.0/message",
    "thid": "<uuid>",
    "jti": "<uuid>",
    "iat": 1760000000,
    "exp": 1760003600,
    "body": {"resourceType": "Bundle", "type": "batch", "data": [], "total": 0},
    "attachments": [{
      "id": "source-xlsx",
      "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "filename": "export.xlsx",
      "data": {"links": ["https://www.dropbox.com/.../export.xlsx?dl=1"]}
    }]
  }'
```

Polling example:

```bash
curl -X POST "https://<host>/publisher/cds-ES/v1/animal-care/<alternate-name>/dataset/qvet-v1.0/excel/_upload-response" \
  -H "Content-Type: application/didcomm-plain+json" \
  -d '{"iss":"did:web:clinic.example:employee:it:loader","type":"https://didcomm.org/plaintext/2.0/message","iat":1760000000,"exp":1760003600,"thid":"<upload-thid>"}'
```

## 7) Windows example

The Windows and PowerShell sequence follows the same `_create`, `_create-response`, `_upload`, and `_upload-response` contract. Keep the same DIDComm fields and just adapt the shell syntax.

## 8) Runtime authentication mode

Business endpoints should use `Authorization: Bearer <access_token>`.

- `id_token` belongs to the identity and exchange flow, not to the DIDComm business payload.
- When `DEMO_MODE=false`, Bearer tokens issued by `/exchange` are mandatory.
- When `DEMO_MODE=true`, legacy compatibility remains temporarily available, but Bearer is still the recommended path.

## 9) What is reused from the current repository

The API contract reuses the existing adapter pipeline, schema normalization, species mapping, and output contract. Deployment changes the transport and persistence model, not the clinical transformation logic.
