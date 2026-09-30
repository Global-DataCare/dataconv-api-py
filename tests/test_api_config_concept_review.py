# Flow contract: derive a row-level resource review queue from API-CONFIG semantics, never from vendor sheet names.
# 1. Read section/family/subfamily/concept/treatment through row-2 mappings.
# 2. Preserve one-to-many candidates and original line text for later human review.
# 3. Do not add inferred clinical claims to the source workbook.

from pathlib import Path

from openpyxl import Workbook
from gdc_data_utils import (
    AllergyIntoleranceClaim,
    ConditionClaim,
    DiagnosticReportClaim,
    ImmunizationClaim,
    MedicationStatementClaim,
    ProcedureClaim,
)

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


def test_includes_every_supported_mapped_local_coding_text_in_the_review_evidence(tmp_path: Path) -> None:
    source = tmp_path / "mapped-clinical-fields.xlsx"
    mapped_claims = [
        AllergyIntoleranceClaim.CODE_TEXT,
        ConditionClaim.CODE_TEXT,
        DiagnosticReportClaim.CODE_TEXT,
        ImmunizationClaim.VACCINE_CODE_TEXT,
        MedicationStatementClaim.CODE_TEXT,
        ProcedureClaim.CODE_TEXT,
    ]
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["API-CONFIG:language=es:subjectKind=animal"])
    sheet.append(mapped_claims)
    sheet.append([f"SOURCE_{index}" for index in range(len(mapped_claims))])
    sheet.append([
        "alergia a penicilina",
        "fractura de sesamoideo",
        "informe de radiología",
        "vacuna antirrábica",
        "amoxicilina",
        "reducción de fractura",
    ])
    workbook.save(source)

    result = classify_workbook(source)

    assert [(item.resource_type, item.source_text) for item in result.rows] == [
        ("AllergyIntolerance", "alergia a penicilina"),
        ("Condition", "fractura de sesamoideo"),
        ("DiagnosticReport", "informe de radiología"),
        ("Immunization", "vacuna antirrábica"),
        ("MedicationStatement", "amoxicilina"),
        ("Procedure", "reducción de fractura"),
    ]
