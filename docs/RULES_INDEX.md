# DataConv repository rules index

This is the navigation entry point for rules owned by the public DataConv
service repository. It grants no gateway, ICA, provider-index, organization or
deployment authority.

## Repository governance

- [`AGENTS.md`](../AGENTS.md) defines scope, authority boundaries, required
  gates and release closure.
- [`README.md`](../README.md) defines the supported service, authorization,
  provider-versus-organization, persistence and local-execution contracts.
- [`pyproject.toml`](../pyproject.toml) owns Python compatibility, package
  metadata and immutable runtime dependencies.
- [`CHANGELOG.md`](../CHANGELOG.md) records tested behavior and contract
  changes.
- [`Dockerfile`](../Dockerfile) owns the immutable container dependency and
  image construction contract; it is not deployment evidence.

## Domain rules

- [`.codex/skills/preserve-fhir-flat-claim-boundaries/SKILL.md`](../.codex/skills/preserve-fhir-flat-claim-boundaries/SKILL.md)
  owns the API-CONFIG, canonical-claim, terminology-review, physical-index and
  FHIR-search separation.
- [`en/13-research-api-config.md`](en/13-research-api-config.md) documents the
  research workbook, review, search and multi-resource boundaries.
- [`en/15-general-clinical-coding.md`](en/15-general-clinical-coding.md)
  documents governed candidate selection and professional review.
- [`en/11-release-staging-production.md`](en/11-release-staging-production.md)
  documents environment-specific image promotion and deployment; live claims
  still require evidence from the exact deployed environment.

## Executable contracts

- [`tests/test_rules_links.py`](../tests/test_rules_links.py) protects this
  locally resolvable rules graph and its provider-authority boundary.
- [`tests/test_container_dependency_contract.py`](../tests/test_container_dependency_contract.py)
  protects the immutable Python claim-catalog dependency.
- [`tests/test_claim_governance.py`](../tests/test_claim_governance.py)
  protects canonical claims and private physical-key separation.
- [`tests/test_research_job_task_search.py`](../tests/test_research_job_task_search.py)
  protects the study-scoped Task search contract.
- [`scripts/run-gcp-adapter-integration.sh`](../scripts/run-gcp-adapter-integration.sh)
  is the canonical external-adapter integration gate when GCP or PostgreSQL
  persistence changes.

Rules from private operations repositories are intentionally absent. Add each
new rule to one canonical owner, link it here and protect material ordering or
safety requirements with an executable contract in the same branch.

