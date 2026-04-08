# 03 - Run And Examples

## Goal

Transform a spreadsheet export from a clinical system into artifacts ready to be delivered.

## Example 1: Qvet (`--dry-run`)

```bash
PYTHONPATH=src python3.11 -m adapter_ingestion \
  --manufacturer qvet \
  --input "/path/to/export/qvet-january.xlsx" \
  --issuer-did "did:web:<example>.globaldatacare.es:employee:<email>:<role>" \
  --audience-did "did:web:<clinic>.globaldatacare.es" \
  --species-catalog-file "./configs/clinic-acme.species.catalog.json" \
  --species-local-map-file "./configs/clinic-acme.species.map.json" \
  --schema-config-file "./configs/clinic-acme.qvet.schema.json" \
  --subject-did-prefix "did:web:<clinic>.globaldatacare.es" \
  --subject-kind animal \
  --data-use secondary \
  --include-fields "FECHA,CONCEPTO,SECCION,FAMILIA,SUBFAMILIA,SUBJECT_ID,ESPECIE,IDARTICULO" \
  --output-dir ./artifacts/qvet \
  --dry-run
```

## Example 2: Wakyma (`--dry-run`)

```bash
PYTHONPATH=src python3.11 -m adapter_ingestion \
  --manufacturer wakyma \
  --input "/path/to/export/wakyma-visits.xlsx" \
  --issuer-did "did:web:<example>.globaldatacare.es:employee:<email>:<role>" \
  --audience-did "did:web:<clinic>.globaldatacare.es" \
  --species-catalog-file "./configs/clinic-acme.species.catalog.json" \
  --species-local-map-file "./configs/clinic-acme.species.map.json" \
  --schema-config-file "./configs/clinic-acme.wakyma.schema.json" \
  --data-use secondary \
  --include-fields "Tipo,Motivo,Mascota,ID Interno Paciente,Fecha+Hora" \
  --output-dir ./artifacts/wakyma \
  --dry-run
```

## Output to inspect

Each `--output-dir` contains at least:

- `composition-message.json`
- `summary.json`

Quick check:

```bash
cat ./artifacts/wakyma/summary.json
```

Fields worth reviewing:

- `recordsTotal`
- `recordsDroppedNoSubjectId`
- `recordsDroppedSectionFilter`
- `adapterReport.unmappedSpeciesCounts`
- `adapterReport.invalidSpeciesCodeCounts`

## Operating rules

- Always run with `--dry-run` first.
- Do not use `--send` while critical mappings are still unresolved.
- Keep a copy of `summary.json` for every upload for auditability.

## Notes

### `Fecha+Hora`

The `+` syntax in `--include-fields` only affects visible XHTML. The clinical FHIR timestamp is computed from `fieldMap.date` plus `fieldMap.time` in the schema.

### `DocumentReference.content*`

- `DocumentReference.text` is only emitted when `dataUse=individual`.
- In `dataUse=secondary`, free-text narrative is intentionally omitted.
- `DocumentReference.contenttype` and `DocumentReference.contentdata` are only used when a real attachment exists.
