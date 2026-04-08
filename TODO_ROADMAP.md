# _TODO-ROADMAP (dataconv-api-py)

Version:
- `0.1.0`
- Date: `2026-04-08`
- Scope: pending implementation tasks aligned with cross-repo security/auth architecture.

## A) API-CONFIG semantics (strict vs non-strict)
- [ ] Define whether non-strict accepts unknown `<ResourceType>_<concrete-param>` columns.
- [ ] Define `_create config` behavior for unknown mappings:
  - [ ] strict mode: reject
  - [ ] non-strict mode: explicit policy (allow+warn OR reject)
- [ ] Define normalization for localized field names.
- [ ] Define deterministic `contained` generation per subject.
- [ ] Define section inference and default fallback behavior.
- [ ] Add compatibility tests for pre-existing mappings.

## B) Tenant API key policy model
- [ ] Keep atomic model: `1 rule = 1 technical consent = 1 ODRL`.
- [ ] Enforce `scope` required.
- [ ] Support `target` + ODRL `instrument` for endpoint/action constraints.
- [ ] Return `consentRef` and `consentModel` in create/search responses.

## C) Blockchain integration stubs (planned)
- [ ] Add adapter interface for anchor operations.
- [ ] Add TODO stubs for:
  - [ ] API key policy anchors
  - [ ] evidence anchors
  - [ ] VC/evidence lifecycle anchors
  - [ ] DCAT catalog publication anchors
- [ ] Expose `anchorStatus` and optional `txId` in operation metadata.

## D) Catalog and collection governance
- [ ] Build catalog from real collection index (resource type/profile aware).
- [ ] Ensure deterministic dataset identifiers.
- [ ] Add tests: ingest -> collection -> dcat catalog.

## E) Docs and contracts
- [ ] Keep `BRIEFING_DATASPACE_EN.md` synced with the canonical workspace file.
- [ ] Add endpoint-level status matrix: `Implemented | Stub | Planned`.
- [ ] Link OpenAPI examples to behavior defined above.
