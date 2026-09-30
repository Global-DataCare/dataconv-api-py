# Revisión general de codificación clínica

DataConv ya disponía de ingestión API-CONFIG, agrupación estable por
ResearchSubject, candidatos de terminología y confirmación humana. La
clasificación previa usa `section`, `family`,
`subfamily`, `concept` y `treatment`; nunca depende del nombre de la hoja ni del
proveedor.

Una fila puede producir varios candidatos revisables. Los tratamientos con
saltos de línea conservan cada línea. Se distinguen candidatos de Procedure,
MedicationStatement, Encounter, Condition, DiagnosticReport, Immunization,
AllergyIntolerance y ChargeItem; lo desconocido queda como `Unclassified`. No
se inventan especie ni sexo.

La ingestión materializa recursos contained revisables para Condition,
Procedure, DiagnosticReport, Immunization, AllergyIntolerance y
MedicationStatement. Una clasificación de vacuna no se convierte en una
administración cuando el texto expresa duda, recomendación o intención futura.
Para borradores importados antes de esta cobertura, la preparación de revisión
puede recuperar una Immunization desde la descripción y fecha del
DocumentReference ya persistido, sin exigir otra subida del Excel.

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

Durante la revisión, el profesional puede repetir la búsqueda con otro texto
acotado, idioma y una fuente terminológica permitida. DataConv ejecuta esa
consulta mediante `ResearchSubject/$review-candidates` y guarda únicamente los
candidatos devueltos por el servicio terminológico.

DataConv envía el nombre canónico de la flat claim mediante el parámetro
`claim`; el servicio de terminología deriva de su capability el resourceType y
el path FHIR. Nunca se convierte por heurística
`Immunization.vaccine-code` en `Immunization.vaccineCode`. Si una consulta no
está disponible, el texto y la propuesta permanecen visibles con cero
candidatos para que la cola de revisión no desaparezca.

Si el destino inferido es incorrecto, `ResearchSubject/$review-reclassify`
mueve la propuesta todavía no resuelta a uno de los destinos clínicos
gobernados (`Condition.code`, `Procedure.code` o `DiagnosticReport.code`). La
operación conserva el texto original y `rowContext`, borra candidatos del
destino anterior y obliga a buscar y confirmar de nuevo contra la terminología
compatible con el nuevo recurso. No convierte LOINC en un código de diagnóstico
ni cambia silenciosamente una propuesta ya revisada.

`ResearchSubject/$review-discard` permite descartar el grafo draft todavía no
revisado de un `thid` de importación exacto cuando el mapping de origen era
incorrecto. La `Task` terminada no se borra: permanece como auditoría. Si existe
alguna decisión ya resuelta, el descarte completo se rechaza para no eliminar
trabajo profesional confirmado.

La clasificación automática combina `section`, `family`, `subfamily`,
`concept`, `treatment`, especie, idioma y el resto de `rowContext`. Las reglas
deterministas crean el primer destino y la terminología aporta candidatos; una
IA puede ordenarlos, pero no confirma códigos. Cada confirmación emite feedback
con contexto, candidatos aceptados y rechazados, revisor y, cuando proceda,
`reclassifiedFrom`. Es material para un dataset supervisado versionado y
evaluado fuera de línea; nunca provoca aprendizaje automático en producción a
partir de una única decisión.

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
