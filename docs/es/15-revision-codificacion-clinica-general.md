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

El texto clínico local original nunca se trunca en las flat claims ni en los
metadatos de revisión. Solo la consulta de candidatos respeta el límite HTTP
del servicio terminológico: no consulta textos de menos de dos caracteres y
usa los primeros 160 cuando el texto es más largo. El profesional sigue viendo
la fuente completa.

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

En esa proyección, `<Resource>.code-text` contiene el texto local original y
canónico; `coding-proposal:*` contiene los candidatos no confirmados y
`<Resource>.code`/`code-display` contienen la selección confirmada. Solo
`coding-proposal:` es un espacio de proyección y no una flat claim FHIR. No se
añade el idioma al nombre del claim; los valores multilingües llevan BCP-47.

Un único `code-text` local se interpreta con `<Resource>.language`. Si existen
varios idiomas, se codifican como una lista CSV de `BCP47|texto`, por ejemplo
`es-ES|sedación,ca-ES|sedació`.

Esta representación sigue el contrato neutral y los ejemplos gobernados de
`fhir-data-utils-ts/coding-review-flat-claims`; no pertenece a SOSChain. En el
mensaje de importación DIDComm, cada propuesta vive en
`body.data[].resource.contained[].meta.codingProposals[]`, junto a
`meta.claims` del recurso clínico correspondiente, y nunca se agrega en
`ResearchSubject.meta`.
