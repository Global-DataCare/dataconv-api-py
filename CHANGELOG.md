# CHANGELOG

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
