# 00 - Modos de operación (qué usar y cuándo)

Este repo tiene dos modos válidos y ambos reutilizan el mismo pipeline de transformación.

## Modo A: CLI local (manual)

Úsalo cuando quieras procesar un fichero en un ordenador local y revisar artefactos antes de enviar.

Comando base:

```bash
PYTHONPATH=src python3 -m adapter_ingestion ... --dry-run
```

Salida:

- Ficheros en `--output-dir` (`composition-message.json`, `summary.json`).
- Opcional `--send` para postear al gateway desde el propio CLI.

## Modo B: API + worker (servicio multi-tenant)

Úsalo cuando el flujo debe ser remoto, multi-tenant y asíncrono.

Procesos:

- `preconversion-api`
- `preconversion-worker`

Flujo (POST-only, estilo gateway):

1. Crear/actualizar configuración tenant:
   `POST /publisher/cds-{jurisdiction}/v1/animal-care/{alternateName}/{softwareId}/config/_create`
2. Subir y encolar conversión:
   `POST /publisher/cds-{jurisdiction}/v1/animal-care/{alternateName}/dataset/{softwareId}/{csv|excel}/_upload`
3. Recuperar respuesta por `thid`:
   `POST /publisher/cds-{jurisdiction}/v1/animal-care/{alternateName}/dataset/{softwareId}/{csv|excel}/_upload-response`
4. El worker genera exactamente los mismos artefactos lógicos del modo CLI, pero en el `BlobStore` configurado.

## Contrato actual de salida (canónico)

- `composition-message.json`:
  - `body.data[]` con `resource=Patient` (recurso principal).
  - `resource.meta.claims` para claims de Patient.
  - `resource.contained[]` incluye `Composition`, `DocumentReference` y `Encounter`.
  - `resource.contained[].meta.claims` contiene claims de cada recurso.
  - `Composition.entry` usa referencias `urn:uuid:<uuid>`.
## Ejemplos versionados

Ver:

- `examples/current-output/composition-message.sample.json`
- `examples/current-output/summary.sample.json`
