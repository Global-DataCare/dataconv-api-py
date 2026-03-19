# 06 - Script rápido para IT

Este script evita recordar comandos largos.

Archivo:

- `scripts/run-clinic-ingestion.sh`

## Cómo usarlo

1. Edita variables en la cabecera del script (input, tenant, DIDs, catálogo, schema).
2. Ejecuta dry-run:

```bash
./scripts/run-clinic-ingestion.sh dry-run
```

3. Revisa `summary.json` en el `OUTPUT_DIR` configurado.
4. Si todo está correcto, exporta `AUTH_TOKEN` y ejecuta:

```bash
export AUTH_TOKEN="<bearer-token>"
./scripts/run-clinic-ingestion.sh send
```

## Variables mínimas que debes tocar

- `MANUFACTURER` (`qvet` o `wakyma`)
- `INPUT_FILE`
- `ISSUER_DID`
- `AUDIENCE_DID`
- `GATEWAY_BASE_URL`
- `SPECIES_CATALOG_FILE`
- `SPECIES_LOCAL_MAP_FILE`
- `SCHEMA_CONFIG_FILE`
- `RESOURCE_ROUTE_PREFIX` (ejemplo: `/v1`)

Variables opcionales (solo si tu API las usa en ruta):

- `TENANT_ID`
- `JURISDICTION`
- `SECTOR`

## Recomendación operativa

- Primeras cargas: `ALLOW_UNMAPPED_SPECIES="true"`.
- Al pasar a operación estable: `ALLOW_UNMAPPED_SPECIES="false"`.
