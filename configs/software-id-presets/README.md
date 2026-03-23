# Software ID presets (autoconfiguración)

Esta carpeta define configuraciones base por `softwareId`.

## Convención

- Nombre de archivo: `<softwareId>.json`
- Ejemplos: `qvet-v1.json`, `wakyma-v1.json`, `appmypets-v1.json`
- El match es exacto por `softwareId` (si el cliente usa `qvet`, el archivo debe llamarse `qvet.json`; si usa `qvet-v1`, debe ser `qvet-v1.json`).

## Cuándo se aplica automáticamente

1. En `_upload` cuando **no existe** config previa para ese tenant+sector+software.
2. En `_create` cuando una entrada no trae `config` explícito.

En ambos casos se aplica merge:

`default_tenant_config_payload` + `preset(<softwareId>)` + `config explícito (si lo hay)`.

## Estructura del preset

El JSON debe seguir el mismo formato de `content` de la configuración tenant:

- `schemaConfig`
  - `headerRowIndex`
  - `fieldMap`
  - opcionales (`fieldDefaults`, `speciesContains`, ...)
- `runtimeDefaults`
  - `language`, `manufacturer`, `subjectKind`, etc.

## Nota sobre `api-config`

`softwareId=api-config` sigue reservado para bootstrap con configuración embebida en el Excel.
No se crea por `_create` manual.
