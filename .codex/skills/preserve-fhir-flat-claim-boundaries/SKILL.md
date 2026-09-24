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
API-CONFIG source mapping: Condition.code-text
Canonical source claim:    resource.meta.claims[Condition.code-text]
Draft-only metadata:       resource.meta.codingProposals[] -> Condition.code
Confirmed additions:       Condition.code + Condition.code-display
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
- For research imports, keep uncoded local-language text in the authoritative
  `<Resource>.<code-field>-text` claim and repeat it in the proposal input as
  review context. Confirmation must not replace it.
- Never serialize `coding-input:*`. That name is neither a flat claim nor an
  API-CONFIG mapping.
- Put `meta.codingProposals[]` beside `meta.claims` on the contained clinical
  resource. Never aggregate proposals on `ResearchSubject.meta`.
- Preserve one primary response Bundle: each converted ResearchSubject belongs
  directly in `body.data[].resource`, and its review metadata belongs at
  `body.data[].resource.contained[].meta.codingProposals[]`. Never introduce a
  `ConversionResult` entry or a second `resource.data[]` Bundle.
- Normalize a historical `Procedure.code-display` value without a matching
  `Procedure.code` to `Procedure.code-text` before terminology review. A display
  becomes authoritative only together with the reviewed terminology code.
- Reuse the neutral builders, paths and package-owned examples from
  `fhir-data-utils-ts`; DataConv mirrors that cross-language contract and does
  not redefine it as a SOSChain rule.

## TDD workflow

1. Add a failing contract test before changing ingestion or search behavior.
2. Prove the API-CONFIG column reaches the canonical record without renaming.
3. Prove the materialized resource contains `@context: org.hl7.fhir.api` and
   the canonical flat claim.
4. Prove `_upload-response` keeps primary resources at `body.data[].resource`,
   rejects a nested `resource.data`, and retains contained coding proposals.
5. Prove the physical index contains the hyphen-preserving key and excludes
   the all-underscore variant.
6. Submit a FHIR `Parameters` search using `code:text` and require a
   `Bundle` of type `searchset` with the expected resource.
7. Run catalog parity, focused DataConv tests, and the full affected suites.

## Research review and storage lifecycle

Preserve this explicit lifecycle in code, tests, and high-level docs:

```text
GCS -> Firestore draft -> human review -> PostgreSQL search index
```

- GCS owns the uploaded workbook and generated job artifacts.
- Firestore receives the processed FHIR-like resources with resource-owned
  `meta.codingProposals[]`; it does not represent the raw side of a
  raw/processed database split.
- Human review is mandatory when terminology codes are inferred from text.
- An accepted professional decision sets the proposal and selected coding to
  `userSelected=true`; this is coding provenance, never workflow state.
- Copy each ResearchSubject to PostgreSQL independently as soon as all of its
  own mandatory proposals are resolved. Keep other subjects in the same import
  available for progressive review without re-upload.
- Load pending review from the durable Firestore ResearchSubject drafts by the
  authorized `ResearchSubject.study`; never require a retained Task, `thid` or
  `_upload-response` artifact to reopen review.
- Preserve ResearchStudy import Tasks outside generic operational TTL cleanup;
  removal requires an explicit governed study/history lifecycle operation.
- For historical drafts that preserve canonical `*-text` but predate proposal
  materialization, run the explicit idempotent `$prepare-review` operation.
  It may retrieve governed terminology candidates and add resource-owned
  `meta.codingProposals[]`, but it must not select a candidate, rewrite the
  source text or require the workbook to be uploaded again.
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

Keep the same governed example in `fhir-data-utils-ts`; DataConv README,
detailed docs and tests reference its contract without inventing alternate
claim paths, code systems, identifiers or UUIDs. State which layer each
representation belongs to and make tests the executable authority.

For research workbook ingestion, keep authorization and transport independent:

- exchange only a GW-signed SMART access token at the actor-neutral
  `/research/auth/_exchange` route;
- accept exact `organization/ResearchSubject.crus?study=...` for the
  DCR-bound, consented professional, or exact create-only
  `organization/ResearchSubject.c?study=...` for the current organization
  controller;
- downscope the former to read/review without upload, accept exact
  `organization/ResearchSubject.rs?study=...` as read/search-only for a
  researcher, and keep upload authority only on the controller profile;
- derive an internal actor profile from that scope and never relabel a
  controller as a professional;
- keep `iss` and `aud` bound to the GW tenant that provides the index. DataConv
  is an internal conversion backend and is never the SMART audience;
- never compare that index-provider identifier with the hosted clinic or
  organization tenant route. Require the latter to have completed its separate
  DataConv onboarding activation;
- do not call `organization/tenant/_activate` during each import. Activation is
  an organization-registration or explicit administration action;
- keep organization registration and controller DCR independent from DataConv
  provisioning. Check `organization/tenant/_status` with the current ICA proof,
  treat `not-configured` as retryable, and use the idempotent `_activate` route;
  dependency unavailability never rolls the organization back;
- treat `/identity/openid/smart/token/_verify` as a documented, unimplemented
  cross-custodian profile until an executable GW route, Swagger operation,
  manager tests, integration tests and live E2E all exist;
- send the workbook as binary multipart and the short-lived JWT only in the
  `Authorization` header;
- read `RESEARCH_WORKBOOK_MAX_BYTES` in DataConv and the portal/BFF with an
  8 MiB default. GW does not receive the workbook and must not define this
  variable;
- treat 2, 8 and 25 MiB as deployment examples. Future DICOM ingestion needs
  separate per-instance, instance-count and aggregate-study limits plus a
  streaming/object-storage design for thousands of files.

The resource/filter scope grammar may later describe appointment permissions,
but no ResearchSubject scope grants scheduling access. Appointment actor,
clinic, practitioner and location constraints require their own tests and
policy contract.

## Terminal research-job notification

- Mark the terminal job and its completion notification as pending in one
  durable control-plane write. Never lose a successful conversion because the
  downstream GW or BFF is unavailable.
- Emit one minimal claims-first Communication through the tenant GW. Reuse the
  upload DIDComm thread as `Communication.identifier`, the exact ResearchStudy
  as subject, the Task as content reference and the Task terminal status as a
  coded content value.
- Address the Communication to the authenticated requesting professional DID;
  do not place an email address, workbook result or clinical rows in the event.
- Let GW own native FHIR R5 Subscription delivery and let the product BFF own
  its authenticated inbox plus browser, push and email fan-out. DataConv owns
  neither surface.
- Retry from persisted job state with a local-only static bearer or production
  workload identity. Never log either credential.
