# AGENTS.md - dataconv-api-py

## Rules entry point

Read [`docs/RULES_INDEX.md`](docs/RULES_INDEX.md) before changing this
repository. It links the repository-owned ingestion, authorization, claims,
storage, testing and release contracts. If linked rules conflict, stop and
reconcile the owning files instead of selecting a convenient interpretation.

## Scope and authority

- This repository owns the DataConv conversion API, worker, controlled
  adapters and research-review persistence flow. It does not own gateway,
  portal, ICA, provider-index or clinical-organization policy.
- A trusted GW index provider supplies the SMART issuer and audience for
  indexed-subject discovery. It is not a clinic, care provider or hosted
  organization. Keep that provider identity separate from the independently
  onboarded organization tenant route.
- DataConv is an internal conversion backend, never the SMART audience and
  never an authority that grants a tenant, sector, controller or professional
  role.

## Canonical data boundaries

- Apply the repository
  [`preserve-fhir-flat-claim-boundaries`](.codex/skills/preserve-fhir-flat-claim-boundaries/SKILL.md)
  skill whenever API-CONFIG mappings, flat claims, terminology review,
  physical index keys or FHIR search parameters change.
- Import canonical Python claim names and normalizers from
  `gdc-data-utils-py`; its generated vocabulary remains subordinate to the
  owning TypeScript catalog described by the skill.
- Keep GCS upload artifacts, Firestore review drafts, human coding decisions
  and PostgreSQL search indexes as distinct lifecycle stages. Never present a
  physical storage key as a canonical claim.

## Required gates

- Use red-green-refactor for every behavior, flow or documentation-contract
  change. The first physical line of every new or modified test module must be
  a complete `# Flow contract:` comment.
- Use a Python version allowed by [`pyproject.toml`](pyproject.toml). Run the
  focused test first and `python -m pytest -q` before merge. When GCP or
  PostgreSQL adapters are affected, run their repository scripts with the
  required integration environment enabled; a skipped integration is not
  passing evidence.
- Keep local tests, external-adapter integration, image construction,
  deployment and authenticated live evidence separate. Do not build or deploy
  an image after a skipped affected gate.
- Work on a branch, update [`CHANGELOG.md`](CHANGELOG.md), merge explicitly
  into `main`, push `main`, verify matching refs and finish with a clean
  worktree.

