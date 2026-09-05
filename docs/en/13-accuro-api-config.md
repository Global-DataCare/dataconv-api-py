# Accuro API-CONFIG workbook flow

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
- Spanish diagnosis/pathology text maps to `DiagnosticReport.code-text`, never
  to `subfamily` or `code-display` without an actual coded concept.
- aggregate catalogue rows without a reliable subject and invoice identity do
  not claim to be Invoice or ChargeItem resources;
- invoice-line rows with a reliable subject and document timestamp receive a
  deterministic `Invoice.identifier` and distinct `ChargeItem.identifier` values.

## DiagnosticReport flat claim and search contract

The API-CONFIG field, persisted flat claim, physical database index, and FHIR
query use related but intentionally different representations:

```text
Excel API-CONFIG
DiagnosticReport.code-text
          ↓
resource.meta.claims
{
  "@context": "org.hl7.fhir.api",
  "DiagnosticReport.code-text": "diagnóstico en español"
}
          ↓ internal indexing
diagnosticreport_code-text
          ↓ FHIR search
DiagnosticReport?code:text=diagnóstico
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
`DiagnosticReport` resources.

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
PYTHONPATH=src .venv/bin/python scripts/prepare-accuro-api-config.py \
  "/path/to/datos espacios de datos Accuro.xlsx" \
  "/path/to/datos espacios de datos Accuro - API-CONFIG.xlsx" \
  --split-dir "/path/to/accuro-organizations" \
  --report "/path/to/accuro-preparation.json"
```

Validate every row and one standard FHIR search per organization:

```bash
PYTHONPATH=src .venv/bin/python scripts/validate-accuro-api-config.py \
  "/path/to/accuro-organizations" \
  --preparation-report "/path/to/accuro-preparation.json" \
  --report "/path/to/accuro-validation.json"
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
