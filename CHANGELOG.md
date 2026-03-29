# CHANGELOG

## 2026-03-28
- Fix: El test de autocreación de configuración por upload (tests/test_api_config_upload_autocreate.py) ahora valida correctamente la lógica sectorizada:
    - Si el sector es "animal-care", speciesFhir se carga desde el archivo default.
    - Si el sector no es "animal-care" o no hay archivo, speciesFhir está presente pero vacío (codes: {}).
    - Nunca se produce error por ausencia de speciesFhir; la configuración se crea siempre.
- Motivo: Robustecer la creación automática de configuración para nuevos tenants/sectores al subir Excel con API-CONFIG, permitiendo extensión posterior por la organización.
- Validación: Test pasa correctamente en ambos escenarios.
