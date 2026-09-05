---
name: preserve-fhir-flat-claim-boundaries
description: Preserve canonical GDC flat FHIR-like claims across API-CONFIG imports, resource.meta.claims, DataConv database indexes, and FHIR search parameters. Use for Excel or CSV mappings, claim catalogs, DiagnosticReport materialization, search_fields normalization, gdc-data-utils-py parity, or queries with FHIR modifiers such as code:text.
---

# Preserve FHIR Flat Claim Boundaries

## Required sources

1. Read the applicable `AGENTS.md`.
2. Import claim names and normalizers from `gdc-data-utils-py`.
3. Treat `gdc-common-utils-ts/src/models/interoperable-claims` as the owning
   vocabulary. Regenerate and test Python parity when that vocabulary changes.
4. Inspect historical tools before porting behavior; do not invent a second
   normalization contract.

## Boundary contract

Keep these representations distinct:

```text
API-CONFIG and resource.meta.claims: DiagnosticReport.code-text
FHIR query parameter:               code:text
DataConv physical search key:       diagnosticreport_code-text
```

- Replace the claim's resource separator `.` with `_` only in the physical
  index key.
- Lowercase the physical key.
- Preserve the `-` inside `code-text`.
- Never emit `diagnosticreport_code_text` for this claim.
- Never expose the physical key in `API-CONFIG`, `meta.claims`, an SDK, or a
  public search contract.
- Use `code-display` only for a display derived from a coded terminology.
  Preserve uncoded local-language diagnosis text as `code-text`.

## TDD workflow

1. Add a failing contract test before changing ingestion or search behavior.
2. Prove the API-CONFIG column reaches the canonical record without renaming.
3. Prove the materialized resource contains `@context: org.hl7.fhir.api` and
   the canonical flat claim.
4. Prove the physical index contains the hyphen-preserving key and excludes
   the all-underscore variant.
5. Submit a FHIR `Parameters` search using `code:text` and require a
   `Bundle` of type `searchset` with the expected resource.
6. Run catalog parity, focused DataConv tests, and the full affected suites.

For Invoice and ChargeItem imports:

1. Require `Invoice.identifier` before grouping invoice lines.
2. Create separate ChargeItem resources and reference them from
   `Invoice.lineItem[].chargeItemReference`.
3. Link every ChargeItem to its Invoice with native `supportingInformation` and
   `ChargeItem.supporting-information`.
4. Use `ChargeItem.part-of` only for another ChargeItem.
5. Reject financial query parameters outside the explicitly tested HL7 R4
   subset instead of treating every flat extension as a standard search.
6. Map the applied-service date to `ChargeItem.occurrence` and prove `code`
   plus repeated `occurrence=ge...`/`occurrence=le...` constraints are AND.
7. Treat cross-family twin filters as AND, but do not claim the gateway E2E is
   complete while GW CORE rejects more than one resource family per request.
   Cross-family OR belongs to multiple SDK searches plus deduplicated union.

## Documentation

Keep the same example in the DataConv README and detailed docs. State which
layer each representation belongs to and make tests the executable authority.
