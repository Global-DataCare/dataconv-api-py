# 12 - Current Output Examples

This document points to real examples of the current output contract.

Generated on **2026-03-01** with:

```bash
PYTHONPATH=src python3.11 -m adapter_ingestion \
  --manufacturer wakyma \
  --input "$HOME/GITS/gdc-workspace/Informes - Explorador de Visitas (Wakyma).xlsx" \
  --tenant-id demo \
  --jurisdiction es \
  --sector veterinary \
  --issuer-did "did:web:example.globaldatacare.es:employee:it:loader" \
  --audience-did "did:web:clinic.globaldatacare.es" \
  --species-catalog-file "./configs/fhir-target-species.template.editable.json" \
  --species-local-map-file "./configs/clinic-species-map.example.json" \
  --schema-config-file "./configs/wakyma.schema.example.json" \
  --include-fields "Tipo,Motivo,Mascota,ID Interno Paciente,Fecha+Hora" \
  --allow-unmapped-species \
  --output-dir ./artifacts/current-example \
  --dry-run
```

## Versioned example files

- `examples/current-output/composition-message.sample.json`
- `examples/current-output/summary.sample.json`

## What to verify

In `composition-message.sample.json`:

- `body.data[0].resource.resourceType = "Patient"`
- `body.data[0].resource.contained[]` includes `Composition`, `DocumentReference`, and `Encounter`
- `Composition.section` and `Composition.type` are LOINC-coded
- `Composition.entry` uses `urn:uuid:<uuid>` references
- `Bundle.entry.fullUrl` is intentionally absent from this pre-conversion payload
- `DocumentReference.contenttype` and `DocumentReference.contentdata` are absent
- `DocumentReference.context` is left empty
- `DocumentReference.text` is omitted for `dataUse=secondary`
- `DocumentReference.text` is present for `dataUse=individual`
