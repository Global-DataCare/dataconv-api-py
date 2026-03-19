# 02 - Configuración de clínica

Este paso se hace una vez por clínica (o cada vez que cambie su software/exportación).

## 1) Elegir adaptador de fabricante

Valores actuales:

- `qvet`
- `wakyma`

Comprobar:

```bash
PYTHONPATH=src python3 -m adapter_ingestion --help
```

## 2) Preparar catálogo de especies de la clínica

Copia el catálogo FHIR estático:

```bash
cp configs/fhir-target-species.template.editable.json configs/clinic-acme.species.catalog.json
```

Estructura clave:

```json
{
  "system": "http://hl7.org/fhir/target-species",
  "codes": {
    "100000108988": "Dogs"
  }
}
```

Regla práctica:

- `codes` no se tocan salvo actualización oficial del catálogo.
- El texto local (`Perro`, `CANINA`, etc.) se mapea aparte con `speciesLocalToFhirCode`.
- Puede variar por software: `Perro`/`Gato` o `CANINA`/`FELINA`/`BOVINA`.

## 2.a) Lista común ES local -> FHIR (recomendada)

Esta lista es transversal (no depende del software):

```bash
cp configs/clinic-species-map.example.json configs/clinic-acme.species.map.json
```

Incluye una base de mascotas y ganado frecuentes para empezar en producción.

## 2.b) Plantilla LOINC de secciones clínicas (obligatoria como base)

Existe una plantilla fija en el repo:

```bash
cp configs/fhir-target-loinc-sections.template.editable.json configs/clinic-acme.loinc.sections.json
```

Uso recomendado:

- Mantener `codes` como catálogo base (`code -> display` en inglés).
- Personalizar solo `clinicDisplayOverrides` para lenguaje local (solo en plantilla LOINC).
- El mapeo operativo `section:family -> code` se define en el schema del fabricante (`loincBySectionFamily`).

## 2.c) Catálogos de `DocumentReference.type` por perfil

En `configs/` hay tres catálogos separados:

- `fhir-documentreference-typecodes.international.veterinary.json`
- `fhir-documentreference-typecodes.international.human.json`
- `fhir-documentreference-typecodes.us.human.json`

Se regeneran desde el HTML oficial con:

```bash
python3 ./scripts/generate-doc-type-catalogs.py
```

## 2.d) Catálogos de Encounter

- Clase de encuentro (`Encounter.class`):
  - `configs/fhir-encounter-class.v3-actcode.template.editable.json`
- Service type (`Encounter.servicetype`):
  - `configs/fhir-encounter-service-type.r4.json`

Se puede regenerar `servicetype` desde el HTML HL7 local con:

```bash
python3 ./scripts/generate-encounter-service-type-catalog.py
```

Regla recomendada:
- usar `encounterClassBySectionFamily` (por defecto `AMB`).
- usar `encounterServiceTypeBySectionFamily` solo cuando tengas un mapeo operativo validado.

## 3) Preparar schema del fabricante (columnas)

### Qvet

```bash
cp configs/qvet.schema.example.json configs/clinic-acme.qvet.schema.json
```

### Wakyma

```bash
cp configs/wakyma.schema.example.json configs/clinic-acme.wakyma.schema.json
```

Puntos importantes:

- `headerRowIndex`: fila donde están cabeceras reales (indexado desde 1).
  - Ejemplo: si fila 1 es título y la cabecera real está en fila 2, usar `headerRowIndex=2`.
  - Si la cabecera está en la primera fila del Excel, usar `headerRowIndex=1`.
  - Si este valor es incorrecto, el adaptador no encuentra columnas como `subjectId`/`FAMILIA` y descarta filas.
- `fieldMap`: mapea columnas origen a campos canónicos.
- `speciesContains`: útil si especie viene embebida dentro de texto (`Mascota = "ZOE (Perro)"`).
  - Usar solo `contains` + `value` (sin códigos).
- `allowedSections`: permite filtrar por secciones válidas (ej.: solo `clinica`).
- `excludedSectionFamilies`: permite excluir categorías por `section:family` (ej.: `clinica:vacunas`).
- `loincBySectionFamily`: mapeo único `section:family -> LOINC` aplicado a `DocumentReference.category` y `Composition.type`.
- `sourceId` es opcional: si no existe, se calcula automáticamente un id estable por fila.

Ejemplo de fragmento:

```json
{
  "allowedSections": ["clinica"],
  "excludedSectionFamilies": ["clinica:vacunas"],
  "loincBySectionFamily": {
    "clinica:laboratorio": "30954-2",
    "clinica:consultas": "34109-9",
    "clinica:cirugia": "11504-8",
    "clinica:medicamentos": "10160-0",
    "clinica:varios": "11503-0"
  }
}
```

Compatibilidad: el adaptador todavía acepta las claves antiguas
`documentCategoryLoincBySectionFamily` y `compositionTypeLoincBySectionFamily`,
pero la recomendada es `loincBySectionFamily`.

## 4) (Opcional) mapping local->code

Usar la lista común y ajustarla por clínica:

```bash
cp configs/clinic-species-map.example.json configs/clinic-acme.species.map.json
```

Formato:

```json
{
  "speciesLocalToFhirCode": {
    "CANINA": "100000108988"
  }
}
```

## 5) Parámetros de identidad (recomendado)

Configura en comandos:

- `--subject-did-prefix`: dominio/base DID de tu organización.
- `--subject-kind animal` (recomendado por ahora).
- `--issuer-did`: formato recomendado `did:web:<dominio>.globaldatacare.es:employee:<email>:<rol>`.
- `--audience-did`: normalmente `did:web:<clinica>.globaldatacare.es`.

Nota: filas sin `subjectId` se descartan.
El `subjectId` se pseudonimiza a multibase (`z...`) usando multihash SHA3-256.

Nota de arquitectura:

- En `gwtemplate-node` se recomienda una HMAC estable por organización para IDs de gemelo digital.
- No asumir rotación directa de esa HMAC: cambiarla requiere migrar/reindexar todos los IDs enlazados.

## 6) Rutas de envío

- Recomendado: `--resource-route-prefix /v1`.
- Legacy opcional: `--tenant-id`, `--jurisdiction`, `--sector`.

## 7) Contenido XHTML en claims

Regla de separación:

- `DocumentReference.text`: narrativa XHTML (tabla de campos) solo en `dataUse=individual`.
- En `dataUse=secondary`, `DocumentReference.text` no se emite.
- `DocumentReference.contenttype/contentdata`: solo para adjuntos reales.
- `DocumentReference.context`: se deja vacío por defecto (no se infiere Appointment/Encounter/EpisodeOfCare).

No se debe mapear el mismo XHTML a `content*`.

## 8) Referencias en Composition

- `Composition.entry` se serializa como `urn:uuid:<uuid>` para referenciar recursos del lote.

## 9) Owner público (Ayuntamiento) y referencias

- Cuando `ownerPublicRules` detecta organización pública, se genera `RelatedPerson`.
- `RelatedPerson.identifier` y `Patient.link` usan el mismo formato:
  - `urn:cds:<PAIS>:v1:organization:multibase:<z...>`
- Si hay más de un owner público, `Patient.link` es una lista separada por comas.
