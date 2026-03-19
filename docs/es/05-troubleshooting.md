# 05 - Troubleshooting

## 1) `Input file not found`

Causa:

- Ruta mal escrita o archivo no accesible.

Acción:

```bash
ls -la "/ruta/al/archivo.xlsx"
```

## 2) `Unknown manufacturer adapter`

Causa:

- `--manufacturer` no soportado.

Acción:

```bash
PYTHONPATH=src python3 -m adapter_ingestion --help
```

Usar uno de los permitidos (`qvet`, `wakyma`).

## 3) `Species mapping is incomplete`

Causa:

- Especies sin resolver.

Acción:

1. Revisar `adapterReport.unmappedSpeciesCounts` en `summary.json`.
2. Añadir/ajustar `speciesLocalToFhirCode` en `species-local-map-file`.
3. Si hace falta, usar `speciesContains` o `species-local-map-file`.

## 4) `invalidSpeciesCodeCounts` con valores

Causa:

- Código en configuración que no existe en catálogo cargado.

Acción:

- Corregir código en `speciesLocalToFhirCode` (o en el origen si ya llega como código FHIR).
- Verificar que el catálogo usado incluya ese code.

## 5) Muchos `recordsDroppedNoSubjectId`

Causa:

- Filas sin `subjectId` (ID interno de paciente/historia).

Acción:

- Verificar columna de `subjectId` en `fieldMap`.
- Validar calidad del export del software origen.

## 6) Error al enviar (`--send`)

Causa frecuente:

- Token inválido, URL incorrecta o conectividad.

Acción:

- Reintentar con `--dry-run` para confirmar transformación.
- Probar conectividad al gateway.
- Verificar `--auth-token` y `--gateway-base-url`.

## 7) Cómo extraer plantilla de especies observadas

```bash
PYTHONPATH=src python3 -m adapter_ingestion \
  --manufacturer qvet \
  --input "/ruta/export.xlsx" \
  --issuer-did "did:web:<example>.globaldatacare.es:employee:<email>:<rol>" \
  --audience-did "did:web:<clinica>.globaldatacare.es" \
  --species-catalog-file "./configs/clinic-acme.species.catalog.json" \
  --species-local-map-file "./configs/clinic-acme.species.map.json" \
  --schema-config-file "./configs/clinic-acme.qvet.schema.json" \
  --export-species-template "./artifacts/species-template.json" \
  --allow-unmapped-species \
  --dry-run
```

## 8) `WARNING: unknown 0.0.0 does not provide the extra 'api'`

Causa:

- `pip`/`setuptools` antiguos no leen correctamente `pyproject.toml`.
- Entorno mezclado (por ejemplo `pip` de Xcode en vez del de tu `.venv`).

Acción:

```bash
cd /ruta/a/adapter-ingestion-py
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip uninstall -y UNKNOWN || true
python -m pip install -e ".[api]"
```

Validación:

```bash
python -m pip show adapter-ingestion-py
preconversion-api --help
preconversion-worker --help
```
