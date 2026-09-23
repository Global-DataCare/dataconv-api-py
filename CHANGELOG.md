# CHANGELOG

## 0.8.7 - 2026-09-23

- Added a controller-proof-protected organization tenant readiness endpoint.
  It reports a missing scoped record as the retryable `not-configured` state
  instead of making portals infer readiness from a failed research request.
- Return every converted primary resource directly in
  `body.data[].resource`; remove the erroneous `ConversionResult` wrapper and
  nested `resource.data[]` Bundle while retaining per-entry response outcomes.
- Materialize review proposals on contained DiagnosticReport resources and
  normalize historical orphan `Procedure.code-display` workbook mappings to
  canonical local `Procedure.code-text` before terminology review.
- Synchronize OpenAPI, integration examples, high-level docs and the local
  flat-claim skill with the canonical coding-review path.
- Save professional decisions progressively and publish each ResearchSubject
  independently only after its own mandatory proposals are resolved; inferred
  source-table, individual or device codes remain unreviewed proposals.
- Stop using `userSelected` as draft/promotion state. Accepted proposals and
  selected codings record `userSelected=true`, including non-generic fields
  such as `Immunization.vaccine-code`.
- Downscope coding reviewers to read/review, add exact read/search-only
  researcher exchange, and reserve upload for the organization controller.

## 0.8.5 - 2026-09-21

- Align DataConv skills, test contracts and examples with the neutral
  `fhir-data-utils-ts` coding-review contract: canonical source `*-text`,
  resource-scoped proposals and no serialized `coding-input:*` fields.

## 0.8.4 - 2026-09-21

- Remove the erroneous serialized `coding-input:<Resource>.code` pseudo-field.
  Imported local clinical wording is now a canonical
  `<Resource>.code-text` flat claim.
- Derive terminology lookup targets internally from canonical local text:
  `Condition.code-text` can propose `Condition.code` without changing or
  overwriting the source-language claim.
- Keep `meta.codingProposals[]` beside `meta.claims` on each contained clinical
  resource; proposals are never aggregated onto the enclosing ResearchSubject.
- Make optional tabular review projections retain canonical source
  `code-text`, while `coding-proposal:*` remains clearly non-authoritative.

## 0.8.3 - 2026-09-21

- Keep imported coding source text exclusively in
  `meta.codingProposals[].inputText` until review instead of prematurely
  claiming it as `<Resource>.code-text`.
- Preserve proposal input after confirmation while writing only the selected
  code and authoritative display to flat claims; local `code-text` remains
  absent until a separately reviewed local text exists.
- Add a collision-free optional tabular projection with distinct
  `coding-input:*`, `coding-proposal:*` and confirmed canonical claim columns.
- Clarify that UI review operates on the FHIR-like ResearchSubject Bundle and
  that CSV/XLSX review files are projections rather than the internal source of
  truth.

## 0.8.2 - 2026-09-21

- Preserve the original source-language `Condition.code-text` through
  terminology review and add `Resource.language`; human confirmation now adds
  code/display without deleting the source text.
- Add BCP-47-aware local-text encoding for flat claims: one base-language value
  stays plain, while multilingual values use CSV-safe `language|text` entries.
- Correct Pinol and Survet treatment narratives from the false
  `Procedure.code-display` mapping to a neutral `treatment` control, and
  materialize reviewable Procedure drafts only when a Procedure coding input is
  actually selected.
- Add sheet-independent, row-level classification of heterogeneous concepts
  into review candidates using section, family, subfamily, concept and
  treatment; do not infer absent species or sex and do not promote candidates
  before human review.
- Keep Elysa immunization enrichment compatible with the current
  `coding-input:Condition.code` diagnosis mapping and emit ignored private
  evidence for the regenerated 13-sheet workbook.

## 0.8.1 - 2026-09-21

- Add a TDD-proven Elysa workbook enrichment that appends canonical
  `Immunization.vaccine-code`, `Immunization.vaccine-code-display` and
  `Immunization.vaccine-code-text` API-CONFIG columns to every sheet.
- Infer reviewable WHO ATCvet candidates for animal vaccination administrations
  and WHO ATC candidates for human administrations while leaving status,
  recommendation, solvent and unrelated dental rows uncoded.
- Emit private CSV, JSON and Markdown evidence with source text, correlated
  code/display/local-text lists, inferred species, confidence and source rows.

## 0.8.0 - 2026-09-19

- Expose study-scoped conversion jobs as canonical flat-claim `Task` resources
  in a FHIR `Bundle` with `type=searchset`. The history is shared by every
  authorized actor for the tenant and ResearchStudy rather than being tied to
  the requester who submitted an import.
- Add the canonical `POST /publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/jobs/Task/_search`
  endpoint with bounded `_count` and `_offset` parameters, exact tenant and
  study filtering, and deterministic newest-first ordering.
- Consume the synchronized `gdc-data-utils-py==0.1.1` Task claim vocabulary.
  JSON:API remains a possible future edge adapter and is not the persisted or
  primary job contract.
- Pin the immutable `gdc-data-utils-py` 0.1.1 GitHub release wheel and verified
  SHA-256 in the container build.

- Keep a trusted GW index provider separate from the hosted organization that
  owns a ResearchStudy import. SMART `iss`/`aud` remain the provider DID while
  DataConv checks the already-onboarded organization tenant route separately;
  the removed one-to-one issuer-to-tenant setting no longer rejects valid
  imports for organizations hosted behind the same index provider.

## 0.7.14 - 2026-09-15

- Send each explicitly confirmed professional terminology choice to the
  channel-neutral reviewed-mapping API even when no coding model is configured.
  The reusable record contains the bounded clinical term and governed context,
  but never the reviewer identity, row context or free-text rationale.
- Preserve the existing privacy-minimal model-evaluation feedback as a separate
  optional sink; exact reviewed matches can now bypass model ranking entirely.

## 0.7.13 - 2026-09-15

- Accept the current organization controller's exact create-only,
  ResearchStudy-pinned GW SMART scope without representing it as a professional;
  retain the professional DCR plus active-Consent `crus` profile and expose one
  actor-neutral RFC 8693 exchange route.
- Reject oversized research workbooks before persistence using the shared
  `RESEARCH_WORKBOOK_MAX_BYTES` setting, defaulting to 8 MiB, while leaving
  DICOM instance/count/aggregate limits to a separate future contract.

## 0.7.12 - 2026-09-06

- Keep the runtime and generated OpenAPI release version synchronized with the
  immutable package and container version declared in `pyproject.toml`.

## 0.7.11 - 2026-09-06

- Keep governed terminology candidates available for human review when the
  optional coding-model ranker is unavailable; such candidates remain
  explicitly unranked and are never auto-selected.
- Add bounded Qvet coding-input rules for clearly clinical allergy, Cushing
  and osteoarthritis follow-up rows, while retail rows remain uncoded, and
  cache duplicate terminology lookups within one conversion job.

## 0.7.10 - 2026-09-06

- Add an RFC 8693 professional ResearchStudy exchange that validates the GW
  SMART access-token signature offline from its allowlisted `did:web` document,
  including `kid`, JWK algorithm, issuer/audience, temporal claims, professional
  subject, exact `HRESCH` purpose and exact study-pinned
  `organization/ResearchSubject.crus` scope.
- Bind every trusted GW issuer explicitly to one active DataConv tenant and
  issue only `dataconv.upload`, `dataconv.read` and `dataconv.review` in a
  short-lived DataConv token carrying the actor and ResearchStudy context.
- Require that professional token and the same ResearchStudy on research
  upload, poll, review patch/batch and ResearchSubject search. Controller
  bootstrap tokens do not substitute for a professional study permission.

## 0.7.9 - 2026-09-06

- Require the same stable `ResearchStudy` correlation for new
  `animal-research` conversions as for `onehealth-research`, including upload
  validation and review promotion. Non-research sectors remain compatible
  without a study reference.

## 0.7.8 - 2026-09-06

- Require the exact network-, sector- and jurisdiction-scoped DataConv tenant
  to be active before exchanging ICA controller proof for a research upload
  token. Inactive or missing tenants now fail with HTTP 403; idempotent tenant
  activation remains the explicit prerequisite.

## 0.7.7 - 2026-09-06

- Add an opt-in shared GKE Ingress route for `/v1/terminology`, targeting a
  configurable Service and Service port in the deployment namespace while the
  catch-all `/` route continues to target the DataConv API.
- Validate the opt-in flag, Kubernetes Service name and port before applying
  the generated Ingress. The terminology route is disabled by default.

- Require every new `onehealth-research` conversion to carry and persist one stable FHIR
  ResearchStudy reference; poll, review patch and ResearchSubject search are
  checked or filtered by that reference.
- Store the public relationship only as the standard `ResearchSubject.study`
  claim. The reference grants no DataConv-local authority and never replaces
  GW Consent or SMART evaluation; legacy unscoped jobs remain pollable but
  cannot be promoted.
- Preserve non-research upload and review compatibility: `researchStudy` is
  optional outside the explicit `onehealth-research` sector.
- Inject the optional terminology and coding-model endpoints, audiences,
  identifiers, timeouts and secret tokens into both GKE workloads through the
  generated ConfigMap and Secret.
- Load the environment-scoped private deployment file before the public
  profile so required secret placeholders can fail closed without forcing
  operators to export credentials into the parent shell.
- Bind review promotion to the conversion job's tenant, jurisdiction, sector
  and software identifier before evaluating its ResearchStudy context.

- Added terminology-service and coding-model HTTP adapters. DataConv sends the
  complete governed candidate set plus allowlisted row context, rejects model-
  invented candidates, and preserves every result for human selection.
- Added provisional `Condition` coding proposals outside authoritative flat
  claims. Human `_patch` review materializes only the selected `Condition.code`
  and English `Condition.code-display`, then emits accepted/rejected feedback
  with the optional reviewer reason.
- Corrected Accuro diagnosis and pathology fields from
  `DiagnosticReport.code-text` to unconfirmed `Condition.code` coding inputs.
- Added proposal and ambiguity counts for portal prioritization and made FHIR
  `code:text` search use confirmed English `code-display` when available.
- Documented and regression-guarded the research lifecycle from GCS upload to
  Firestore review draft and human-confirmed PostgreSQL search promotion.
- Clarified that PostgreSQL duplicates the same processed promoted resource as
  a read optimization, while queries operate on normalized flat-claim search
  fields.
- Recorded the coding-assistance safety boundary: inferred terminology codes
  remain human-reviewed proposals; the deployed worker still uses
  `NoopCodingAssistant`, and remote inference plus durable review-decision
  capture are now configurable; they remain disabled when the service URLs are
  absent.
- Defined the future terminology boundary around FHIR R4 text-filtered
  ValueSet expansion, code validation, and explicit ConceptMap translation;
  general intent or question-answering model endpoints do not substitute for
  an authoritative terminology service.

## 0.7.5 - 2026-09-05

- Scope private Cloud SQL settings to the selected deployment environment so a
  Canada rollout cannot inherit the historical Europe staging database.
- Restart API and worker pods after ConfigMap or Secret rotation so a same-
  digest deployment cannot keep stale runtime settings.

## 0.7.4 - 2026-09-05

- Inject the exact OIDC issuer/audience and session-token secret into GKE so staging cannot silently accept insecure ID-token assertions.
- Unified the package and OpenAPI runtime version so immutable Canada staging
  deployment evidence identifies the actual DataConv release.
- Repaired the production image build after the obsolete separate Spanish
  README had been removed from the repository.
- Pinned the separately released Apache-2.0 `gdc-data-utils-py` wheel and its
  SHA-256 in the production image instead of relying on an unpublished PyPI
  dependency.

- Added a route-scoped controller research exchange that revalidates the fresh
  OIDC plus Connect ICA proof and returns only a short-lived
  `dataconv.upload` token bound to the legal tenant identifier.

- Added Connect ICA-backed organization tenant activation using signed OIDC and
  controller VP evidence; tenant-scoped Bearer tokens can no longer cross into
  another tenant route.
- Separated searchable twin storage by network, jurisdiction, sector and legal
  tenant identifier without changing the public `tenant_id`.
- Replaced plaintext/deterministic subject aliases with a dedicated encrypted
  external-identifier-to-random-twin-UUID store. Firestore deployments require
  an independently managed 32-byte protection key; twin resources remain
  ordinary searchable FHIR-like data.
- Removed identifying Accuro columns from prepared secondary-use workbooks and
  fail closed when a non-UUID secondary subject has no confidential resolver.

- Accuro Excel preparation now adds one embedded `API-CONFIG` mapping per
  organization sheet, repairs missing or duplicate headers, assigns reusable
  private-namespace UUIDs, and emits one uploadable workbook per tenant.
- Secondary-use conversion now exposes `ResearchSubject` as the public twin
  aggregate while preserving `Subject` for individual data flows.
- Research search accepts a FHIR `Parameters` resource and returns a FHIR
  `Bundle` of type `searchset`; confirmed `ResearchSubject` resources are
  promoted and indexed idempotently.
- Added executable per-sheet contracts and full-source preparation/validation
  commands for the 13 supplied Accuro datasets.
- Accuro mappings now preserve last appointment as
  `appointment_lastoccurrencedate`, derive an estimated `subject_birthyear`
  from appointment year and age when needed, and replace full birth dates with
  the year before writing prepared workbooks.
- Animal and clinic names are redacted from prepared secondary-use sheets,
  `origin` is intentionally left unmapped, and Spanish free-text diagnoses are
  mapped to `DiagnosticReport.code-text` rather than `subfamily` or
  code-display.
- API-CONFIG flat DiagnosticReport claims are now transported into canonical
  resources and searchable with the FHIR `code:text` modifier. The internal
  index maps `DiagnosticReport.code-text` to `diagnosticreport_code-text`,
  preserving the field-name hyphen.
- DataConv now consumes canonical claim catalogs and boundary normalizers from
  `gdc-data-utils-py` instead of defining the DiagnosticReport contract locally.
- Added governed BaseConfig classification and a reconciler that separates
  control, canonical, DataConv-extension and pending mappings without
  overwriting the supplied workbook.
- Added Invoice and ChargeItem materialization with deterministic identifiers,
  native Invoice line-item references and `ChargeItem.supporting-information`;
  `ChargeItem.part-of` is reserved for parent ChargeItems.
- Enforced the documented HL7 R4 financial search subset and reject unsupported
  extension fields with HTTP 400.
- Map applied-line dates to `ChargeItem.occurrence`; repeated search parameters
  are AND constraints, comma-separated alternatives are OR within one
  parameter, and `code:text` supports case-insensitive contains matching.
- Document that multi-resource twin AND remains a GW CORE gap and that
  cross-family OR is a high-level SDK union rather than one ambiguous request.

## 2026-07-23
- Aligned integrator guides, examples and GCP bootstrap documentation with the
  current Data Space artifact and configuration backlog.

## 2026-04-08 16:01:44 PDT
- Documentation navigation: moved roadmap/briefing references and the primary docs entry points to the top of the root README so repo orientation appears before operational details.
- Repository guidance: added publishable root-level roadmap and briefing references without machine-specific absolute paths.

## 2026-04-08 15:39:55 PDT
- Release: bumped package version to `0.7.1` after the `0.7.0` branch release line had already accumulated additional documentation and exchange-configuration cleanup changes.

## 2026-04-08 15:02:00 PDT
- Auth exchange: added explicit exceptional profile `api-key-exception.v1` for non-confidential desktop clients, gated by `LOCAL_EXCHANGE_ALLOW_API_KEY_EXCEPTION=true`.
- Security behavior: API-key-only exchange is now rejected unless the explicit profile is requested and enabled.
- Token exchange manager: added tenant API key resolution path without email binding for exceptional mode (`resolve_policy_without_email`) while preserving the existing id_token + VP flow.
- Tenant API key provisioning now returns consent-style metadata per atomic rule (`consentRef`, `consentModel=one-rule-one-consent-one-odrl`).
- Local static API-key exchange env names are now explicit `LOCAL_*` only:
  - `LOCAL_EXCHANGE_ALLOW_API_KEY`
  - `LOCAL_EXCHANGE_ALLOW_API_KEY_EXCEPTION`
  - `LOCAL_EXCHANGE_API_KEYS`
  - `LOCAL_EXCHANGE_API_KEY_SUBJECT_DEFAULT`
  - `LOCAL_EXCHANGE_API_KEY_ORG_DEFAULT`
- OpenAPI: token exchange schema/operation docs now describe the explicit exceptional profile and include a dedicated example.
- Tests: added unit coverage in `tests/test_token_exchange_manager.py` and updated exchange flow tests with the new profile example.

## 2026-04-08 14:42:33 PDT
- Environment templates: clarified the semantic difference between general API key exchange for organization-controlled clients and the exception-only `api-key-exception.v1` profile for non-confidential devices.

## 2026-04-08 14:02:09 PDT
- Environment templates: translated the remaining Spanish comments in example `.env` files to English so the public-facing configuration templates are language-consistent.

## 2026-04-08 14:00:59 PDT
- Environment templates: made the local/static API-key exception flag explicit by environment policy, enabled in local and staging examples and disabled in production example.
- Documentation hygiene: replaced personal absolute home paths in the root README with `$HOME`-based shell examples.

## 2026-04-08 13:47:43 PDT
- Documentation: consolidated the root README into a single English operational guide and removed the separate `README_es.md` entry point.
- Documentation: promoted the English docset under `docs/en/` as the canonical reference set while keeping `docs/es/` as the Spanish archive.

## 2026-04-08 13:45:34 PDT
- Repository hygiene: normalized `.gitignore` by removing duplicated blocks and consolidating local environment, cache, log, and secret patterns.
- Git review safety: `.env.*.example` files are no longer hidden by ignore rules, so example templates remain visible for review and staging.
- Documentation cleanup: replaced the remaining stale repository path references from `adapter-ingestion-py` to `dataconv-api-py` in English and Spanish operational docs.

## 2026-04-08 11:11:39 PDT
- Documentation: added a primary English docset under `docs/en/` covering installation, clinic configuration, runbooks, API contract, deployment, storage adapters, release flow, and GCP bootstrap.
- Documentation entry points: `README.md`, `docs/README.md`, `INTEGRATORS_GUIDE.md`, and `TEST-api-config.md` now point to English content first while preserving Spanish material as archive/reference.
- Branching: the documentation work is being carried on branch `0.7.0`.

## 2026-04-08 11:00:22 PDT
- Python runtime alignment: local development guidance now explicitly uses `python3.11` to match the current Docker base image.
- Packaging metadata: `pyproject.toml` now requires Python 3.11 or newer, preventing installs on 3.8-3.10 that were no longer aligned with deployment.
- Docs: `README.md` and `README_es.md` now explain that `venv` inherits the interpreter resolved by the shell and add verification commands before creating `.venv`.

## 2026-04-02
- Docs/OpenAPI: V2-first auth guidance for business endpoints now prioritizes `Authorization: Bearer <access_token>` and clarifies `id_token` belongs to identity/exchange steps.
- Docs/OpenAPI examples: removed legacy `id_token`/`vp_token` from main DIDComm business examples (`_upload`, `_upload-response`, config create/poll examples).
- OpenAPI schemas: legacy body fields `id_token` and `vp_token` are marked deprecated with compatibility-only descriptions.
- Auth compatibility: in `DEMO_MODE=true`, invalid Bearer tokens now fall back safely to legacy demo parsing flow instead of hard-failing immediately.
- Deployment: `scripts/deploy-gke.sh` now propagates `PRECONV_AUTH_MODE` and `DEMO_MODE` into ConfigMap generation.
- Tests: updated OpenAPI assertions to current tag/layout behavior and added regression coverage for demo-mode legacy fallback.

## 2026-03-28
- Fix: El test de autocreación de configuración por upload (tests/test_api_config_upload_autocreate.py) ahora valida correctamente la lógica sectorizada:
    - Si el sector es "animal-care", speciesFhir se carga desde el archivo default.
    - Si el sector no es "animal-care" o no hay archivo, speciesFhir está presente pero vacío (codes: {}).
    - Nunca se produce error por ausencia de speciesFhir; la configuración se crea siempre.
- Motivo: Robustecer la creación automática de configuración para nuevos tenants/sectores al subir Excel con API-CONFIG, permitiendo extensión posterior por la organización.
- Validación: Test pasa correctamente en ambos escenarios.
