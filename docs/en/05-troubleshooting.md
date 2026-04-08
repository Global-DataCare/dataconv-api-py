# 05 - Troubleshooting

## 1) `Input file not found`

Verify the path, quoting, and file permissions. Use an absolute path first if needed.

## 2) `Unknown manufacturer adapter`

The current supported adapters are `qvet` and `wakyma`. Confirm the value passed in `--manufacturer` and check the CLI help:

```bash
PYTHONPATH=src python3.11 -m adapter_ingestion --help
```

## 3) `Species mapping is incomplete`

The export contains local species names that are not mapped to FHIR target-species codes yet. Update your clinic species map and rerun `--dry-run`.

## 4) `invalidSpeciesCodeCounts` contains values

Your mapping produced codes that are not valid in the configured FHIR target-species catalog. Keep the official `speciesFhir.codes` catalog unchanged and only adjust `speciesLocalToFhirCode`.

## 5) High `recordsDroppedNoSubjectId`

Rows without `subjectId` are discarded on purpose. Check the schema `fieldMap.subjectId` value against the real spreadsheet header names.

## 6) Gateway delivery errors with `--send`

Confirm the following before retrying:

- The same input succeeds with `--dry-run`
- The Bearer token is valid and not expired
- The gateway accepts the token audience and issuer
- The route prefix is correct for the target gateway

## 7) How to extract a species template from observed data

Run a dry run first and inspect the adapter report in `summary.json` to identify unmapped species values. Then add only the missing local labels to the clinic map.

## 8) `WARNING: unknown 0.0.0 does not provide the extra 'api'`

Cause:

- Old `pip` or `setuptools`
- Mixed environments, especially when `pip` comes from Xcode or another interpreter instead of the active `.venv`

Fix:

```bash
cd /path/to/dataconv-api-py
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip uninstall -y UNKNOWN || true
python -m pip install -e ".[api]"
```

Validation:

```bash
python -m pip show adapter-ingestion-py
preconversion-api --help
preconversion-worker --help
```
