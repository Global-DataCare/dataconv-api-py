# Elysa Immunization coding workbook

The enrichment command creates a derived workbook and never overwrites the
source. Every sheet receives these canonical flat-claim mappings in row 2:

```text
Immunization.vaccine-code
Immunization.vaccine-code-display
Immunization.vaccine-code-text
```

The code value is CSV with `system|code` entries. Display and Spanish text are
CSV in the same order; standard CSV quoting preserves commas inside official
displays. The first four animal sheets use WHO ATCvet and the last three human
sheets use WHO ATC. A sheet can legitimately contain only empty values, as the
dental source does.

This step records international terminology candidates, not commercial
product identifiers or regional authorisations. Exact product or explicit
administration text may support an ATC/ATCvet inference, but ambiguous
formulations retain multiple candidates or a broader group and remain marked
for review. Solvents, recommendations, vaccination-status statements and
unrelated rows are not converted into Immunization claims.

Run with Python 3.11 and the Excel extra installed:

```bash
PYTHONPATH=src python scripts/enrich-elysa-immunizations.py \
  "/private/source/2026-08-31- Elysa - tratameintos - API-CONFIG.xlsx" \
  "/private/results/2026-08-31- Elysa - tratameintos - API-CONFIG - IMMUNIZATION-CODED.xlsx" \
  --evidence-dir "/private/results/elysa-immunization-coding"
```

The evidence directory contains a human-readable summary plus CSV and JSON
records with original text, candidates, international displays, Spanish text,
inferred NCBI species codes, confidence and matched source rows. These files
contain source clinical text and must remain outside the public repository.
