# General clinical concept review

DataConv already had API-CONFIG ingestion, stable ResearchSubject grouping,
governed terminology candidates and human confirmation. Heterogeneous
`section`, `family`, `subfamily`, `concept` and `treatment` values first produce
review-only resource candidates. Sheet and vendor names are not classification
inputs.

The internal review document is the FHIR-like Bundle. Each source identifier
is resolved to its stable secondary-use UUID, repeated rows update the same
ResearchSubject, and its `contained` array holds sibling Composition and
clinical resources. `Composition.entry` references those resources. The portal
must render `meta.codingProposals[]` from this Bundle; the CSV below is only a
diagnostic/export projection.

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

An optional tabular review projection keeps three namespaces separate:

```text
Condition.code-text                         original imported local text
coding-proposal:Condition.code              candidate system|code list
coding-proposal:Condition.code-display      candidate official displays
coding-proposal:Condition.code-text         candidate local texts, if supplied
Condition.code / code-display / code-text   confirmed flat claims only
```

Only `coding-proposal:*` is a projection namespace and not a FHIR flat claim.
The source is already canonical `<Resource>.code-text`. No language suffix is
added to a claim name. When local texts have multiple languages, their values
carry BCP-47 tags.

For confirmed local text flat claims, a single value uses the resource language and stays
plain. Multiple translations use CSV-safe `BCP47|text` entries, for example
`es-ES|sedación,ca-ES|sedació`. Code and display lists remain correlated by
coding; concept-level local texts are not assumed to be one-to-one with codes.
