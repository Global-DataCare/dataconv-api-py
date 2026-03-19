# 07 - Mapeo LOINC clínico (Qvet/Wakyma)

Este documento aterriza un mapeo práctico para usar códigos LOINC en:

- `DocumentReference.category` (categoría documental).
- `Composition.type` (tipo de sección clínica agregada).

Plantilla base en repo:

- `configs/fhir-target-loinc-sections.template.editable.json`

## 1) Mapeo operativo recomendado

| Origen (`section:family`) | LOINC code (single mapping) |
|---|---:|
| `clinica:laboratorio` | `30954-2` |
| `clinica:consultas` | `34109-9` |
| `clinica:cirugia` | `11504-8` |
| `clinica:medicamentos` | `10160-0` |
| `clinica:varios` | `11503-0` |

Notas:

- `ANESTESIA` se puede mapear a `11485-0` (anesthesia records).
- Si quieres omitir categorías (por ejemplo vacunas), usa `excludedSectionFamilies` en `schemaConfig`.
- Si no hay mapeo explícito, el adaptador usa fallback LOINC genérico.

## 2) Códigos del listado HL7/FHIR que encajan bien en este caso

- `11369-6` History of Immunization.
- `11485-0` Anesthesia records.
- `11488-4` Consult Note.
- `11504-8` Surgical operation note.
- `18842-5` Discharge summary (alta tras ingreso, también válido en veterinaria).
- `18726-0` Radiology studies (set).
- `18748-4` Diagnostic imaging study.
- `26436-6` Laboratory studies (set).
- `26441-6` Cardiology studies (set) para electrocardiografía.
- `28570-0` Procedure note (si se quiere más foco en procedimiento).
- `34109-9` Evaluation and management note.
- `47045-0` Study report document (genérico).
- `47046-8` Summary of death (defunción, cuando aplique).
- `56445-0` Medication summary document.
- `57133-1` Referral note (solo si realmente es derivación).
- `15508-5` Labor and delivery records (partos veterinarios, según casuística del centro).
- `29750-7` Neonatal intensive care records (casos específicos; no común).

## 3) Códigos no clínicos o de uso condicionado

Regla práctica de configuración por clínica:

- Se permiten códigos de alta, nacimiento y defunción cuando el flujo veterinario los use.
- Políticas de privacidad (`57017-6`, `57016-8`) no deben mezclarse con historia clínica.
- Comunicación no clínica general (`47049-2`) solo si hay un caso funcional explícito.
- Registros de tienda/venta no entran en este flujo clínico (se reservarán para flujo `schema.org` en otra fase).

## 4) Relación con catálogos internos del proyecto

Este mapeo es compatible con:

- `clinical-sections.en.ts` (catálogo de secciones clínicas en inglés).
- `medicalHistoryClassification` de `Loinc.ts` (secciones IPS y ampliaciones).

Se recomienda mantener en producción una lista blanca por clínica en:

- `loincBySectionFamily`

y revisar periódicamente las entradas con fallback genérico.
