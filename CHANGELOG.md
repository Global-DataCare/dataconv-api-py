# CHANGELOG

## 2026-04-08 13:47:43 PDT
- Documentation: consolidated the root README into a single English operational guide and removed the separate `README_es.md` entry point.
- Documentation: promoted the English docset under `docs/en/` as the canonical reference set while keeping `docs/es/` as the Spanish archive.

## 2026-04-08 13:45:34 PDT
- Repository hygiene: normalized `.gitignore` by removing duplicated blocks and consolidating local environment, cache, log, and secret patterns.
- Git review safety: `.env.*.example` files are no longer hidden by ignore rules, so example templates remain visible for review and staging.
- Documentation cleanup: replaced the remaining stale repository path references from `adapter-ingestion-py` to `dataconv-api-py` in English and Spanish operational docs.

## 2026-04-08 15:02:00 PDT
- Auth exchange: added explicit exceptional profile `api-key-exception.v1` for non-confidential desktop clients, gated by `EXCHANGE_ALLOW_API_KEY_EXCEPTION=true`.
- Security behavior: API-key-only exchange is now rejected unless the explicit profile is requested and enabled.
- Token exchange manager: added tenant API key resolution path without email binding for exceptional mode (`resolve_policy_without_email`) while preserving the existing id_token + VP flow.
- Tenant API key provisioning now returns consent-style metadata per atomic rule (`consentRef`, `consentModel=one-rule-one-consent-one-odrl`).
- OpenAPI: token exchange schema/operation docs now describe the explicit exceptional profile and include a dedicated example.
- Tests: added unit coverage in `tests/test_token_exchange_manager.py` and updated exchange flow tests with the new profile example.

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
