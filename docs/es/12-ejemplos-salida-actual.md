# 12 - Ejemplos de salida actual

Este documento apunta a ejemplos reales del contrato actual de salida.

Generados el **1 de marzo de 2026** con:

```bash
PYTHONPATH=src python3 -m adapter_ingestion \
  --manufacturer wakyma \
  --input "/Users/fernando/GITS/gdc-workspace/Informes - Explorador de Visitas (Wakyma).xlsx" \
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

## Archivos de ejemplo (versionados)

- `examples/current-output/composition-message.sample.json`
- `examples/current-output/summary.sample.json`

## Qué comprobar

- En `composition-message.sample.json`:
  - `body.data[0].resource.resourceType = "Patient"`.
  - `body.data[0].resource.contained[]` contiene `Composition`, `DocumentReference` y `Encounter`.
  - `Composition.section` y `Composition.type` van codificados con LOINC (`http://loinc.org|<code>`).
  - `Composition.entry` referencia recursos con `urn:uuid:<uuid>`.
  - No se incluye `Bundle.entry.fullUrl` en este payload de preconversión.
  - No aparecen `DocumentReference.contenttype` ni `DocumentReference.contentdata`.
  - No aparece `DocumentReference.context` (se deja vacío por falta de enlace fiable a Appointment/Encounter/EpisodeOfCare).
  - En `dataUse=secondary` no se incluye `DocumentReference.text`.
  - En `dataUse=individual` sí se incluye `DocumentReference.text` (XHTML narrativo).
