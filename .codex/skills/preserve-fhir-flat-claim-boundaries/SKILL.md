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

Keep these representations distinct for terminology-assisted research import:

```text
API-CONFIG source mapping: coding-input:Condition.code
Draft-only metadata:       meta.codingProposals[]
Confirmed flat claims:     Condition.code + Condition.code-display
FHIR query parameters:     code and code:text
```

- Replace the claim's resource separator `.` with `_` only in the physical
  index key.
- Lowercase the physical key.
- Preserve the `-` inside `code-text`.
- Never emit `diagnosticreport_code_text` for this claim.
- Never expose the physical key in `API-CONFIG`, `meta.claims`, an SDK, or a
  public search contract.
- Use `code-display` only for the English display returned with a governed
  terminology code.
- For research imports, keep uncoded local-language diagnosis text in the
  proposal input, not in authoritative `<Resource>.code-text` claims.

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

## Research review and storage lifecycle

Preserve this explicit lifecycle in code, tests, and high-level docs:

```text
GCS -> Firestore draft -> human review -> PostgreSQL search index
```

- GCS owns the uploaded workbook and generated job artifacts.
- Firestore receives the processed FHIR-like resources as review drafts with
  `userSelected=true`; it does not represent the raw side of a raw/processed
  database split.
- Human review is mandatory when terminology codes are inferred from text.
- Confirmation updates those same resources to `userSelected=false` and copies
  them to the PostgreSQL search repository.
- PostgreSQL stores the exact `claims`, derived `search_fields`, and the same
  complete processed `resource`; searches filter `search_fields` and return
  `resource`.
- Describe the duplicated promoted resource as a read optimization, never as a
  distinct semantic version. Any change to this duplication requires an
  explicit source-of-truth and reconciliation contract.

Coding assistance is proposal-only. The terminology service must return every
candidate allowed by sector, jurisdiction, resource and field. The model may
rank that closed set with `recommendationPercent` and `evidence`, but it must
never add a candidate, approve a proposal or promote a draft. Persist accepted
and rejected human decisions plus an optional reason through
`/v1/coding/feedback` before treating them as a governed, de-identified,
human-reviewed evaluation or training corpus. Never train online from a single
review and never treat model output as its own label.

Verify the runtime constructor and environment before claiming AI integration.
The worker uses `NoopCodingAssistant` whenever either the terminology URL or
coding-model URL is absent. With both configured, require executable tests for
candidate retrieval, closed-set ranking and review feedback delivery.

Treat a reusable model runtime as infrastructure behind separate, scoped
adapters. Intent classification, question answering, and terminology coding are
not interchangeable API contracts. For clinical coding, require an
authoritative terminology service and preserve the FHIR R4 operations in docs,
JSDoc, snippets, and boundary tests:

- [`ValueSet/$expand?filter=`](https://hl7.org/fhir/R4/valueset-operation-expand.html)
  discovers text-filtered candidates within an explicit value set;
- [`ValueSet/$validate-code`](https://hl7.org/fhir/R4/valueset-operation-validate-code.html)
  validates the reviewed candidate;
- [`ConceptMap/$translate`](https://hl7.org/fhir/R4/conceptmap-operation-translate.html)
  maps an identified code to another governed coding system.

Allow a model to normalize source text and rank returned candidates. Never let
it invent an authoritative code, choose an unconstrained system, or replace
terminology validation. Apply separately configured value sets and profile or
jurisdiction restrictions for condition, observation/test, procedure, and
other resource families.

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
