# Flow contract: derive a row-level resource review queue from API-CONFIG semantics, never from vendor sheet names.
# 1. Read section/family/subfamily/concept/treatment through row-2 mappings.
# 2. Preserve one-to-many candidates and original line text for later human review.
# 3. Do not add inferred clinical claims to the source workbook.

from pathlib import Path

from openpyxl import Workbook

from adapter_ingestion.api_config_concept_review import classify_workbook


def test_classifies_api_config_rows_without_mutating_workbook(tmp_path: Path) -> None:
    source = tmp_path / "prepared.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "arbitrary-vendor-name"
    sheet.append(["API-CONFIG:language=es:subjectKind=animal"])
    sheet.append(["section", "family", "subfamily", "concept", "treatment"])
    sheet.append(["SECTION", "FAMILY", "SUBFAMILY", "CONCEPT", "TREATMENT"])
    sheet.append(["TIENDA", "HIGIENE", "TOALLITAS", "Toallitas 40 unidades", ""])
    sheet.append(["CLINICA", "OFTALMOLOGÍA", "", "Control", "trusopt 1 gota 2 veces al día\npreforte 1 gota 3 veces al dia"])
    workbook.save(source)

    result = classify_workbook(source)

    assert [(item.row_number, item.resource_type, item.source_text) for item in result.rows] == [
        (4, "ChargeItem", "Toallitas 40 unidades"),
        (5, "MedicationStatement", "trusopt 1 gota 2 veces al día"),
        (5, "MedicationStatement", "preforte 1 gota 3 veces al dia"),
    ]
    assert result.counts_by_resource_type == {"ChargeItem": 1, "MedicationStatement": 2}
    assert source.exists()
