# 03 - Ejecución y ejemplos

## Objetivo

Transformar un export del software clínico en artefactos listos para envío.

## Ejemplo 1: Qvet (dry-run)

```bash
PYTHONPATH=src python3 -m adapter_ingestion \
  --manufacturer qvet \
  --input "/ruta/export/listados mes de enero Qvet.xlsx" \
  --issuer-did "did:web:<example>.globaldatacare.es:employee:<email>:<rol>" \
  --audience-did "did:web:<clinica>.globaldatacare.es" \
  --species-catalog-file "./configs/clinic-acme.species.catalog.json" \
  --species-local-map-file "./configs/clinic-acme.species.map.json" \
  --schema-config-file "./configs/clinic-acme.qvet.schema.json" \
  --subject-did-prefix "did:web:<clinica>.globaldatacare.es" \
  --subject-kind animal \
  --data-use secondary \
  --include-fields "FECHA,CONCEPTO,SECCION,FAMILIA,SUBFAMILIA,SUBJECT_ID,ESPECIE,IDARTICULO" \
  --output-dir ./artifacts/qvet \
  --dry-run
```

## Ejemplo 2: Wakyma (dry-run)

```bash
PYTHONPATH=src python3 -m adapter_ingestion \
  --manufacturer wakyma \
  --input "/ruta/export/Informes - Explorador de Visitas (Wakyma).xlsx" \
  --issuer-did "did:web:<example>.globaldatacare.es:employee:<email>:<rol>" \
  --audience-did "did:web:<clinica>.globaldatacare.es" \
  --species-catalog-file "./configs/clinic-acme.species.catalog.json" \
  --species-local-map-file "./configs/clinic-acme.species.map.json" \
  --schema-config-file "./configs/clinic-acme.wakyma.schema.json" \
  --data-use secondary \
  --include-fields "Tipo,Motivo,Mascota,ID Interno Paciente,Fecha+Hora" \
  --output-dir ./artifacts/wakyma \
  --dry-run
```

## Salidas a revisar

En cada `--output-dir`:

- `composition-message.json` (`data[].resource=Patient` con `contained[]` de `Composition`, `DocumentReference` y `Encounter`)
- `summary.json`

Comprobar rápido:

```bash
cat ./artifacts/wakyma/summary.json
```

Campos relevantes:

- `recordsTotal`
- `recordsDroppedNoSubjectId`
- `recordsDroppedSectionFilter`
- `adapterReport.unmappedSpeciesCounts`
- `adapterReport.invalidSpeciesCodeCounts`

## Reglas de operación

- Siempre ejecutar primero con `--dry-run`.
- No enviar (`--send`) mientras haya mapeos pendientes críticos.
- Guardar copia de `summary.json` por trazabilidad de cada carga.

## Nota sobre `Fecha+Hora`

- `--include-fields` con `+` (`Fecha+Hora`) solo afecta al XHTML visible.
- La fecha clínica FHIR se calcula por `fieldMap.date` + `fieldMap.time` del schema.

## Nota sobre `DocumentReference.content*`

- `DocumentReference.text` solo se incluye cuando `dataUse=individual`.
- En `dataUse=secondary` se omite para no exponer narrativa libre.
- `DocumentReference.contenttype/contentdata` se usarán solo cuando exista un adjunto real.
