# 06 - Quick Script For IT

This helper script avoids repeating long CLI commands.

Script:

- `scripts/run-clinic-ingestion.sh`

## How to use it

1. Edit the variables at the top of the script: input file, tenant, DIDs, species catalog, and schema.
2. Run a dry run:

```bash
./scripts/run-clinic-ingestion.sh dry-run
```

3. Review `summary.json` in the configured `OUTPUT_DIR`.
4. If everything is correct, export `AUTH_TOKEN` and run:

```bash
export AUTH_TOKEN="<bearer-token>"
./scripts/run-clinic-ingestion.sh send
```

## Minimum variables to update

- `MANUFACTURER` (`qvet` or `wakyma`)
- `INPUT_FILE`
- `ISSUER_DID`
- `AUDIENCE_DID`
- `GATEWAY_BASE_URL`
- `SPECIES_CATALOG_FILE`
- `SPECIES_LOCAL_MAP_FILE`
- `SCHEMA_CONFIG_FILE`
- `RESOURCE_ROUTE_PREFIX` such as `/v1`

Optional variables for APIs that still use them in the route:

- `TENANT_ID`
- `JURISDICTION`
- `SECTOR`

## Operational recommendation

- For first-time uploads: `ALLOW_UNMAPPED_SPECIES="true"`
- For stable operation: `ALLOW_UNMAPPED_SPECIES="false"`
