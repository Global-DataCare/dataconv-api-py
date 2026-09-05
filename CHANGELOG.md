# CHANGELOG

## Unreleased

- Inject the exact OIDC issuer/audience and session-token secret into GKE so staging cannot silently accept insecure ID-token assertions.

## 0.7.4 - 2026-09-05

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
