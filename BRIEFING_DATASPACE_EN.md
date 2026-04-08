# BRIEFING_DATASPACE_EN

Version control:
- Document: `BRIEFING_DATASPACE_EN`
- Version: `1.0.0`
- Status: `Canonical (derived from ES canonical briefing)`
- Date: `2026-04-08`
- Canonical ES source: workspace-level `BRIEFING_DATASPACE_ES.md`
- This EN canonical file: repository root `BRIEFING_DATASPACE_EN.md`

## 1. Purpose
Single baseline document for project leadership, security audit, and engineering.
It defines actors, identity/access flows, and boundaries across ICA, GW, DataConversion, and SDKs.

## 2. Canonical actors
- `service-controller`: governs service-internal operator endpoints.
- `tenant-controller`: governs one hosted organization.
- `tenant-runtime-client`: backend/app/device that calls day-to-day runtime APIs.

Rule:
- avoid ambiguous terms (`admin`, `platform-controller`) in technical docs.

## 3. Service boundaries
- ICA: identity/compliance, verifiable credentials, DID Document, evidence lifecycle.
- GW: multi-organization node operations (messaging, policies, consent/rules).
- DataConversion: ingestion, transformation, digital twin, dataset/catalog publication.
- SDKs: integration clients (Node/Python/frontend), not policy substitutes.

## 4. Authentication profiles
- `identity-exchange.v1`: `/_dcr -> /_code -> /_token -> /_exchange`.
- `smart-backend.v1`: `client_credentials + private_key_jwt` (SMART standard profile).
- `api-key-exception.v1`: exceptional non-confidential profile (explicit opt-in only).

Current boundaries:
- ICA and GW do not assume `api-key-exception.v1` as default runtime behavior.
- DataConversion may expose it only as an explicit auditable exception.

## 5. API-key policy (mandatory)
- atomic model: `1 rule = 1 technical consent = 1 ODRL`.
- `scope` mandatory per rule.
- `target` and ODRL `instrument` strongly recommended.
- explicit status and expiry.

## 6. Internal management vs tenant runtime
- `service-controller` routes should be deployment-restricted.
- recommended convention: `LOCAL_MANAGEMENT_SECTOR=host`.
- tenant runtime stays under `tenant-id` + associated authorization.

## 7. Auditability requirements
- log actor/action/object scope (`tenantId`, `purpose`, `keyVersion`, `consentRef`, `thid`).
- blockchain-ready integrations should expose `anchorStatus`, optional `anchorRef/txId`.

## 8. Data/catalog requirements (DataConversion)
- define strict/non-strict behavior for API-CONFIG mappings.
- define deterministic `contained` grouping and section fallback behavior.
- expose DCAT catalogs derived from real collections.

## 9. Documentation governance
- ES file is the canonical source.
- EN file is the cross-repo distribution baseline.
- each repo should keep an EN copy with canonical reference and version header.
