# 02 - Clinic Configuration

This setup is usually done once per clinic, or whenever the vendor software or export format changes.

## 1) Choose the manufacturer adapter

Current values:

- `qvet`
- `wakyma`

Check the available options with:

```bash
PYTHONPATH=src python3.11 -m adapter_ingestion --help
```

## 2) Prepare the clinic species catalog

Copy the static FHIR species catalog:

```bash
cp configs/fhir-target-species.template.editable.json configs/clinic-acme.species.catalog.json
```

Relevant structure:

```json
{
  "system": "http://hl7.org/fhir/target-species",
  "codes": {
    "100000108988": "Dogs"
  }
}
```

Practical rules:

- Keep `codes` aligned with the official catalog.
- Map local labels such as `Perro`, `CANINA`, or `BOVINA` separately through `speciesLocalToFhirCode`.
- Local wording often varies by clinic and by source software.

### 2.a) Shared local-to-FHIR species map

```bash
cp configs/clinic-species-map.example.json configs/clinic-acme.species.map.json
```

This file gives you a shared starting point for common pets and livestock names.

### 2.b) LOINC template for clinical sections

```bash
cp configs/fhir-target-loinc-sections.template.editable.json configs/clinic-acme.loinc.sections.json
```

Recommended usage:

- Keep `codes` as the base code-to-display catalog.
- Only customize `clinicDisplayOverrides` for local language needs.
- Define the operational `section:family -> code` mapping in the manufacturer schema using `loincBySectionFamily`.

### 2.c) `DocumentReference.type` catalogs

Available catalogs in `configs/`:

- `fhir-documentreference-typecodes.international.veterinary.json`
- `fhir-documentreference-typecodes.international.human.json`
- `fhir-documentreference-typecodes.us.human.json`

Regenerate them from the official HTML tables with:

```bash
python3.11 ./scripts/generate-doc-type-catalogs.py
```

### 2.d) Encounter catalogs

- `Encounter.class`: `configs/fhir-encounter-class.v3-actcode.template.editable.json`
- `Encounter.serviceType`: `configs/fhir-encounter-service-type.r4.json`

Regenerate service types with:

```bash
python3.11 ./scripts/generate-encounter-service-type-catalog.py
```

Recommended rule:

- Use `encounterClassBySectionFamily` with `AMB` as the default.
- Only configure `encounterServiceTypeBySectionFamily` when you have a validated operational mapping.

## 3) Prepare the manufacturer schema

### Qvet

```bash
cp configs/qvet.schema.example.json configs/clinic-acme.qvet.schema.json
```

### Wakyma

```bash
cp configs/wakyma.schema.example.json configs/clinic-acme.wakyma.schema.json
```

Important fields:

- `headerRowIndex`: row number containing the real headers, starting from 1.
- `fieldMap`: maps source columns to canonical fields.
- `speciesContains`: useful when species is embedded in another text field.
- `allowedSections`: keep only valid sections.
- `excludedSectionFamilies`: filter categories such as `clinica:vacunas`.
- `loincBySectionFamily`: unique `section:family -> LOINC` mapping used by `DocumentReference.category` and `Composition.type`.
- `sourceId`: optional. When omitted, the adapter generates a stable identifier from row content.

Example:

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

Legacy compatibility still exists for `documentCategoryLoincBySectionFamily` and `compositionTypeLoincBySectionFamily`, but `loincBySectionFamily` is the supported key.

## 4) Optional local-text to code mapping

```bash
cp configs/clinic-species-map.example.json configs/clinic-acme.species.map.json
```

Example:

```json
{
  "speciesLocalToFhirCode": {
    "CANINA": "100000108988"
  }
}
```

## 5) Identity settings

Recommended command-line parameters:

- `--subject-did-prefix`: base DID domain for your organization
- `--subject-kind animal`
- `--issuer-did`: `did:web:<domain>.globaldatacare.es:employee:<email>:<role>`
- `--audience-did`: usually `did:web:<clinic>.globaldatacare.es`

Rows without `subjectId` are dropped. The adapter pseudonymizes `subjectId` into multibase format (`z...`) using SHA3-256 multihash.

## 6) Delivery routes

- Recommended: `--resource-route-prefix /v1`
- Legacy optional: `--tenant-id`, `--jurisdiction`, `--sector`

## 7) XHTML narrative

- `DocumentReference.text` is only emitted for `dataUse=individual`.
- For `dataUse=secondary`, `DocumentReference.text` is suppressed.
- `DocumentReference.contenttype` and `DocumentReference.contentdata` are reserved for real attachments.
- `DocumentReference.context` is intentionally left empty by default.

## 8) `Composition` references

`Composition.entry` uses `urn:uuid:<uuid>` to reference resources inside the batch.

## 9) Public owner handling

When `ownerPublicRules` detects a public organization, the pipeline creates a `RelatedPerson`. Both `RelatedPerson.identifier` and `Patient.link` use the same public organization identifier format:

- `urn:cds:<COUNTRY>:v1:organization:multibase:<z...>`
