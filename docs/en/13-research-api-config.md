# Research workbook API-CONFIG flow

The supplied source workbook contains 13 organization sheets with different
schemas. DataConv upload routes are tenant-scoped, so the combined prepared
workbook is a review artifact and the generated organization workbooks are the
operational upload inputs.

Each prepared sheet has this layout:

1. row 1: `API-CONFIG` plus language, software id, subject kind and secondary-use mode;
2. row 2: DataConv internal field names from the agnostic mapping catalog;
3. row 3: source headers, with missing and duplicate headers repaired;
4. remaining rows: source data plus `RESEARCH_SUBJECT_ID` and, where needed, a stable record date.

UUIDs are derived with a randomly generated private namespace. The namespace
is stored beside the combined output as `<output>.subject-namespace` and is
reused when the same output is regenerated. Keep that sidecar private and with
the prepared workbooks. Rows with a reliable source subject key share one UUID;
rows without one receive a row-scoped pseudonym rather than being merged by an
unsafe guess.

Privacy and semantic corrections applied during preparation:

- last-visit columns map to `appointment_lastoccurrencedate`; when they are also
  the best available record date, a separate `RECORD_DATE` copy is generated;
- when age and a dated visit exist, `SUBJECT_BIRTHYEAR` is estimated as visit
  year minus age;
- a full source birth date is replaced by its year before the prepared workbook
  is written;
- animal names and clinic/legal clinic names are blanked after private subject
  pseudonym resolution;
- `origin` is not mapped until a governed source-role vocabulary is selected;
- diagnosis/pathology text maps to canonical `Condition.code-text`; DataConv
  also exposes the same source value as `meta.codingProposals[].inputText`
  while proposing `Condition.code`, and never overwrites the local text;
- Pinol and Survet treatment narratives map to neutral `treatment` input, not
  to `Procedure.code-display`; classification and terminology review decide
  whether each line represents a Procedure, medication use or neither;
- aggregate catalogue rows without a reliable subject and invoice identity do
  not claim to be Invoice or ChargeItem resources;
- invoice-line rows with a reliable subject and document timestamp receive a
  deterministic `Invoice.identifier` and distinct `ChargeItem.identifier` values.

## Condition coding-input and search contract

The API-CONFIG field, persisted flat claim, physical database index, and FHIR
query use related but intentionally different representations:

```text
Excel API-CONFIG
Condition.code-text
          ↓
resource.meta.claims
{
  "@context": "org.hl7.fhir.api",
  "Condition.code-text": "diagnóstico en español",
  "Condition.language": "es-ES"
}
meta.codingProposals[]
{
  "field": "Condition.code",
  "inputText": "diagnóstico en español"
}
          ↓ internal indexing
condition_code-text
          ↓ FHIR search
Condition?code:text=diagnóstico
```

Only the resource separator `.` becomes `_` in the physical index. The hyphen
inside `code-text` is preserved. `diagnosticreport_code_text` is not a valid
physical representation of this claim. The physical key never appears in
API-CONFIG, `meta.claims`, SDK contracts, or FHIR queries.

A FHIR `Parameters` request uses the same modifier:

```json
{
  "resourceType": "Parameters",
  "parameter": [
    {
      "name": "code:text",
      "valueString": "diagnóstico en español"
    }
  ]
}
```

DataConv returns a `Bundle` with `type: searchset` containing matching
`Condition` resources after review promotion. The source local text remains in
both the canonical claim and proposal context before and after code
confirmation.

## Invoice and ChargeItem contract

Financial API-CONFIG mappings use canonical dotted claims. Physical-looking
legacy fields such as `invoice_date` or `chargeitem_quantity` are aliases in the
mapping catalogue, not valid canonical API-CONFIG claims.

```text
Invoice.identifier
Invoice.date
ChargeItem.identifier
ChargeItem.code
ChargeItem.code-text
ChargeItem.occurrence
ChargeItem.quantity-number
ChargeItem.quantity-unit
```

Rows sharing the same safe invoice identity materialize as one `Invoice` with
multiple line items. Each line is a separate `ChargeItem`:

```text
Invoice.lineItem[].chargeItemReference -> urn:uuid:ChargeItem
ChargeItem.supportingInformation       -> urn:uuid:Invoice
ChargeItem.supporting-information      -> urn:uuid:Invoice
```

`ChargeItem.part-of` is accepted only for an actual parent ChargeItem. It is
not used to link the invoice. Standard DataConv searches are limited to
`Invoice` (`date`, `identifier`, `issuer`, `recipient`, `status`, `subject`) and
`ChargeItem` (`code`, `identifier`, `occurrence`, `subject`). Repeated values
of one parameter are AND constraints; comma-separated alternatives within one
value are FHIR OR alternatives. `code:text` performs a case-insensitive
contains match over `DiagnosticReport.code-text`.

The invoice-line workbook maps `FECHA_LINEA` to `ChargeItem.occurrence`, the
date when the charged service or product was applied, rather than merely to a
generic control date. A useful single-resource search is therefore:

```text
ChargeItem?code=<system>|<product-code>
  &occurrence=ge2026-01-01
  &occurrence=le2026-03-31
```

A query that combines `ChargeItem` and `DiagnosticReport` criteria is a
multi-resource twin operation, with all criteria interpreted as AND. DataConv
can materialize the two resource families, but current GW CORE twin search
still rejects more than one resource-scoped family per request. Cross-family
AND and its DataConv-to-GW E2E must not be reported as implemented yet. OR
between resource families is performed by the high-level SDK as multiple
searches followed by a deduplicated union.

The supplied aggregate service catalogue has no safe invoice identity and its
financial-looking columns remain intentionally unmapped. The invoice-line
dataset derives its invoice UUID from the private namespace, subject identifier
and document timestamp, so lines of one document share the Invoice without
exposing the source subject identifier.

Prepare the workbooks:

```bash
PYTHONPATH=src .venv/bin/python scripts/prepare-research-api-config.py \
  "/path/to/source-research-data.xlsx" \
  "/path/to/prepared-research-data.xlsx" \
  --split-dir "/path/to/research-organizations" \
  --report "/path/to/research-preparation.json"
```

Validate every row and one standard FHIR search per organization:

```bash
PYTHONPATH=src .venv/bin/python scripts/validate-research-api-config.py \
  "/path/to/research-organizations" \
  --preparation-report "/path/to/research-preparation.json" \
  --report "/path/to/research-validation.json"
```

The public secondary-use resource is `ResearchSubject`. Search accepts a FHIR
`Parameters` body and returns `Bundle.type = searchset`:

```json
{
  "resourceType": "Parameters",
  "parameter": [
    {
      "name": "identifier",
      "valueUri": "urn:uuid:<research-subject-uuid>"
    }
  ]
}
```

This aligns DataConv and GW CORE at the public resource and request/response
contract. It does not make both services one index, and it does not transfer
identifier authority: when DataConv data is published into GW CORE, GW must
still resolve and assign its own registered tenant-private twin alias.

## Reproducible search fixtures

Generate the veterinary and non-dental human-health workbooks for provisional
Study A and Study B with:

```bash
PYTHONPATH=src .venv/bin/python scripts/generate-research-search-workbooks.py \
  examples/research-search
```

The source-shaped `DATA` sheets end at `CONCEPTO`. They repeat only a synthetic
original-patient identifier; the configured confidential subject-link resolver
replaces it with the same stable ResearchSubject UUID across rows, later
imports and manual additions. No ResearchSubject UUID or derived FHIR claim is
carried as an extra source column. The clinical concepts reproduce
representative patterns from the supplied tables. The
`SEARCH_CASES` sheet covers vaccine, diagnosis, procedure, allergy, diagnostic
report, medication, quantitative HbA1c Observation, birth-year and
clinical-date criteria.

The human Study A fixture contains the positive subject A, value-negative
subject B and condition/date-negative subject C. Study B contains subject D
with the same clinical profile as A but a distinct UUID. The same search plan
must therefore return A only inside Study A and D only inside Study B.

Single-resource plans, including date ranges, execute directly. Plans that
combine birth year with immunization or combine different clinical resources
are marked `planner-required`: the assistant must issue the individual
resource searches and intersect their subject identifiers inside the exact
authorized ResearchStudy. This is not represented as a made-up FHIR search
parameter. `tests/test_research_search_workbooks.py` executes both categories
against the generated clinical resources and verifies the expected subjects.
