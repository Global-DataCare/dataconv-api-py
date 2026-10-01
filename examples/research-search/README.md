# Research search Excel fixtures

This directory contains four generated, anonymous acceptance fixtures:

- `research-search-veterinary-study-a.xlsx` and
  `research-search-veterinary-study-b.xlsx` use representative veterinary
  concept text for rabies vaccination, diagnoses, procedures, allergies,
  diagnostic reports, medication and encounters.
- `research-search-human-study-a.xlsx` and
  `research-search-human-study-b.xlsx` use representative non-dental
  human-health text, including influenza vaccination, diabetes, quantitative
  HbA1c observations and medication.

Each workbook contains:

1. `DATA`: source-shaped API-CONFIG input ending at `CONCEPTO`. It carries only
   a synthetic `ORIGINAL_PATIENT_ID`, mapped to `personal_id`; the confidential
   resolver replaces it with the same stable UUID in every row and later
   import. No ResearchSubject UUID or derived FHIR column travels in the source
   workbook.
2. `SEARCH_CASES`: Spanish natural-language questions, the expected
   resource/search plan, expected subject identifiers and whether the current
   single-resource search can execute it directly.
3. `README`: cohort, exact provisional ResearchStudy and privacy constraints.

Study A contains subjects A, B and C. In the human fixture, A has diabetes,
HbA1c 8.4% and metformin; B has diabetes but HbA1c 6.2%; C has HbA1c 9.1% but
no diabetes and an out-of-range date. Study B contains D with the same clinical
profile as A and a different stable subject UUID. This proves study isolation.

`single-resource` cases are executable with the current search repository.
`subject-intersection` cases deliberately describe the missing assistant
planner: execute each resource search, extract its subject identifiers and
intersect the sets inside the authorized ResearchStudy. A single invented FHIR
parameter must not replace that operation.

Regenerate all four files from the repository root:

```bash
PYTHONPATH=src .venv/bin/python scripts/generate-research-search-workbooks.py \
  examples/research-search
```

The executable contract is `tests/test_research_search_workbooks.py`.
