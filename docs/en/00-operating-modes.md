# 00 - Operating Modes

This repository supports two valid execution modes. Both reuse the same transformation pipeline and produce the same logical artifacts.

## Mode A: Local CLI

Use the CLI when you want to process one file on a workstation, inspect the artifacts, and optionally send them later.

Base command:

```bash
PYTHONPATH=src python3.11 -m adapter_ingestion ... --dry-run
```

Expected output:

- Files in `--output-dir`, typically `composition-message.json` and `summary.json`.
- Optional `--send` to post the generated payloads directly to the gateway.

## Mode B: API plus worker

Use the API plus worker mode when the flow must be remote, multi-tenant, and asynchronous.

Processes:

- `preconversion-api`
- `preconversion-worker`

Typical flow:

1. Create or update tenant configuration:
   `POST /publisher/cds-{jurisdiction}/v1/animal-care/{alternateName}/{softwareId}/config/_create`
2. Upload and enqueue a conversion job:
   `POST /publisher/cds-{jurisdiction}/v1/animal-care/{alternateName}/dataset/{softwareId}/{csv|excel}/_upload`
3. Poll the asynchronous response by `thid`:
   `POST /publisher/cds-{jurisdiction}/v1/animal-care/{alternateName}/dataset/{softwareId}/{csv|excel}/_upload-response`
4. The worker writes the same logical artifacts produced by the CLI into the configured BlobStore.

## Canonical output contract

`composition-message.json` is the canonical pre-conversion payload. It contains:

- `body.data[]` with `resource=Patient` as the primary resource.
- `resource.meta.claims` for patient-level claims.
- `resource.contained[]` with `Composition`, `DocumentReference`, and `Encounter`.
- `resource.contained[].meta.claims` with claims for each contained resource.
- `Composition.entry` references serialized as `urn:uuid:<uuid>`.

## Versioned examples

See:

- `examples/current-output/composition-message.sample.json`
- `examples/current-output/summary.sample.json`
