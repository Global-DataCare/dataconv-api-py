# Revisión general de codificación clínica

DataConv ya disponía de ingestión API-CONFIG, agrupación estable por
ResearchSubject, candidatos de terminología y confirmación humana. La
clasificación previa usa `section`, `family`,
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

La fuente interna de la revisión es el Bundle FHIR-like. Las filas repetidas se
agrupan bajo el mismo UUID de ResearchSubject; `ResearchSubject.contained`
contiene como hermanos la Composition y los recursos clínicos, enlazados por
`Composition.entry`. La UI consume sus `meta.codingProposals[]`. Un Excel o CSV
es únicamente una proyección opcional.

En esa proyección, `coding-input:<Resource>.code` contiene el texto original,
`coding-proposal:*` contiene los candidatos y los nombres canónicos
`<Resource>.code`, `code-display` y `code-text` contienen solo lo confirmado.
Los prefijos `coding-input:` y `coding-proposal:` no son flat claims FHIR. No se
añade el idioma al nombre del claim; los valores multilingües llevan BCP-47.

Un único `code-text` local se interpreta con `<Resource>.language`. Si existen
varios idiomas, se codifican como una lista CSV de `BCP47|texto`, por ejemplo
`es-ES|sedación,ca-ES|sedació`.
