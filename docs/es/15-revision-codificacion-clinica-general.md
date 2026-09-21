# Revisión general de codificación clínica

DataConv ya disponía de ingestión API-CONFIG, candidatos de terminología y
confirmación humana. La clasificación previa usa `section`, `family`,
`subfamily`, `concept` y `treatment`; nunca depende del nombre de la hoja ni del
proveedor.

Una fila puede producir varios candidatos revisables. Los tratamientos con
saltos de línea conservan cada línea. Se distinguen candidatos de Procedure,
MedicationStatement, Encounter, DiagnosticReport, Immunization y ChargeItem;
lo desconocido queda como `Unclassified`. No se inventan especie ni sexo.

```bash
PYTHONPATH=src .venv/bin/python scripts/classify-api-config-concepts.py \
  "/privado/Elysa-API-CONFIG.xlsx" \
  --evidence-dir "/privado/resultados/revision-conceptos"
```

El comando no modifica el Excel. El CSV puede contener texto clínico y debe
guardarse en `artifacts/` u otra ubicación privada ignorada. Clasificar no
confirma ni crea el recurso definitivo: la revisión humana y la selección de
terminología son fases posteriores y separadas.

Un único `code-text` local se interpreta con `<Resource>.language`. Si existen
varios idiomas, se codifican como una lista CSV de `BCP47|texto`, por ejemplo
`es-ES|sedación,ca-ES|sedació`.
