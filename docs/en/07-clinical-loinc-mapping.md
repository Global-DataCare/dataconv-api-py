# 07 - Clinical LOINC Mapping For Qvet And Wakyma

This guide provides a practical mapping for LOINC codes used in:

- `DocumentReference.category`
- `Composition.type`

Base template in the repository:

- `configs/fhir-target-loinc-sections.template.editable.json`

## 1) Recommended operational mapping

| Source (`section:family`) | LOINC code |
|---|---:|
| `clinica:laboratorio` | `30954-2` |
| `clinica:consultas` | `34109-9` |
| `clinica:cirugia` | `11504-8` |
| `clinica:medicamentos` | `10160-0` |
| `clinica:varios` | `11503-0` |

Notes:

- `ANESTESIA` can be mapped to `11485-0`.
- To exclude categories such as vaccines, use `excludedSectionFamilies` in `schemaConfig`.
- If no explicit mapping exists, the adapter falls back to a generic LOINC code.

## 2) Useful HL7/FHIR codes for this scenario

- `11369-6` History of Immunization
- `11485-0` Anesthesia records
- `11488-4` Consult Note
- `11504-8` Surgical operation note
- `18842-5` Discharge summary
- `18726-0` Radiology studies
- `18748-4` Diagnostic imaging study
- `26436-6` Laboratory studies
- `26441-6` Cardiology studies
- `28570-0` Procedure note
- `34109-9` Evaluation and management note
- `47045-0` Study report document
- `47046-8` Summary of death
- `56445-0` Medication summary document
- `57133-1` Referral note
- `15508-5` Labor and delivery records
- `29750-7` Neonatal intensive care records

## 3) Codes to use conditionally

Recommended practical rule per clinic:

- Allow discharge, birth, and death codes only when the veterinary workflow actually needs them.
- Keep privacy-policy and non-clinical communication codes out of clinical history.
- Retail or sales records do not belong in this clinical flow.

## 4) Relationship to internal project catalogs

This mapping is compatible with:

- `clinical-sections.en.ts`
- `medicalHistoryClassification` in `Loinc.ts`

In production, keep a clinic-specific allow-list in `loincBySectionFamily` and review generic fallback entries periodically.
