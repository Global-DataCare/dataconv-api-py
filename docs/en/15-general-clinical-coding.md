# General clinical concept review

DataConv already had API-CONFIG ingestion, governed terminology candidates and
human confirmation. The remaining boundary is now explicit: heterogeneous
`section`, `family`, `subfamily`, `concept` and `treatment` values first produce
review-only resource candidates. Sheet and vendor names are not classification
inputs.

One source row may yield more than one candidate. Multiline treatment is split
without losing its original lines. Medication-like instructions remain
`MedicationStatement` candidates; procedures, encounters, diagnostic reports,
immunizations and retail `ChargeItem` rows are separated by semantic hierarchy.
Unknown values remain `Unclassified`. No absent species or sex is inferred.

Generate a private row-level CSV and summary from a prepared workbook:

```bash
PYTHONPATH=src .venv/bin/python scripts/classify-api-config-concepts.py \
  "/private/Elysa-API-CONFIG.xlsx" \
  --evidence-dir "/private/results/concept-review"
```

The command never changes the workbook and the output can contain clinical
text, so it belongs under `artifacts/` or another ignored private directory.
Classification does not create authoritative resources or terminology codes;
the review decision and terminology confirmation are separate phases.

For local text flat claims, a single value uses the resource language and stays
plain. Multiple translations use CSV-safe `BCP47|text` entries, for example
`es-ES|sedación,ca-ES|sedació`. Code and display lists remain correlated by
coding; concept-level local texts are not assumed to be one-to-one with codes.
