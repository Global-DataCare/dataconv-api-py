# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from gdc_data_utils import (
    AllergyIntoleranceClaim,
    ConditionClaim,
    DiagnosticReportClaim,
    ImmunizationClaim,
    MedicationStatementClaim,
    ProcedureClaim,
)

from adapter_ingestion.ai.base import NoopCodingAssistant
from adapter_ingestion.manufacturers.registry import get_adapter
from adapter_ingestion.models import AdapterContext
from adapter_ingestion.pipeline import run_pipeline
from adapter_ingestion.runtime.adapters.search import _search_fields
from adapter_ingestion.service.api_config import extract_embedded_api_config


def _context(schema_config: dict) -> AdapterContext:
    return AdapterContext(
        manufacturer="api-config",
        tenant_id="clinic-a",
        jurisdiction="ES",
        sector="onehealth-research",
        issuer_did="did:web:issuer.example",
        audience_did="did:web:audience.example",
        subject_did_prefix="urn:uuid",
        subject_kind="animal",
        strict_species_mapping=False,
        data_use="secondary",
        schema_config=schema_config,
    )


def test_api_config_keeps_uncoded_diagnosis_as_condition_review_proposal() -> None:
    csv_text = (
        "API-CONFIG:language=es:subjectKind=animal:dataUse=secondary\n"
        f"date,subject_id,section,family,{ConditionClaim.CODE_TEXT}\n"
        "FECHA,SUJETO,SECCION,FAMILIA,DIAGNOSTICO\n"
        "2026-03-19,11111111-1111-4111-8111-111111111111,clinica,diagnostico,Otitis externa\n"
    )
    with NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        tmp.write(csv_text)
        path = Path(tmp.name)
    try:
        embedded = extract_embedded_api_config(path)
        assert embedded is not None
        assert embedded["schemaConfig"]["fieldMap"][ConditionClaim.CODE_TEXT] == "DIAGNOSTICO"

        records = get_adapter("api-config").read_records(
            path,
            _context(embedded["schemaConfig"]),
        )
    finally:
        path.unlink(missing_ok=True)

    assert records[0].flat_claims == {ConditionClaim.CODE_TEXT: "Otitis externa"}
    assert records[0].coding_inputs == {ConditionClaim.CODE: "Otitis externa"}

    result = run_pipeline(records, _context(embedded["schemaConfig"]), NoopCodingAssistant())
    aggregate = result.composition_message["body"]["data"][0]["resource"]
    assert not any(
        resource.get("resourceType") == "DiagnosticReport"
        for resource in aggregate["contained"]
    )
    condition = next(
        resource
        for resource in aggregate["contained"]
        if resource.get("resourceType") == "Condition"
    )
    assert "Condition.code" not in condition["meta"]["claims"]
    assert condition["meta"]["claims"][ConditionClaim.CODE_TEXT] == "Otitis externa"
    assert condition["meta"]["claims"]["Condition.verification-status"] == "provisional"
    assert condition["meta"]["codingProposals"][0]["field"] == "Condition.code"
    assert condition["meta"]["codingProposals"][0]["inputText"] == "Otitis externa"
    assert condition["meta"]["codingProposals"][0]["candidates"] == []


def test_explicit_diagnostic_report_text_remains_a_diagnostic_report_claim() -> None:
    csv_text = (
        "API-CONFIG:language=es:subjectKind=animal:dataUse=secondary\n"
        "date,subject_id,section,family,DiagnosticReport.code-text\n"
        "FECHA,SUJETO,SECCION,FAMILIA,DIAGNOSTICO\n"
        "2026-03-19,11111111-1111-4111-8111-111111111111,clinica,diagnostico,Informe radiológico\n"
    )
    with NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        tmp.write(csv_text)
        path = Path(tmp.name)
    try:
        embedded = extract_embedded_api_config(path)
        assert embedded is not None
        records = get_adapter("api-config").read_records(path, _context(embedded["schemaConfig"]))
    finally:
        path.unlink(missing_ok=True)

    result = run_pipeline(records, _context(embedded["schemaConfig"]), NoopCodingAssistant())
    aggregate = result.composition_message["body"]["data"][0]["resource"]
    diagnostic_report = next(
        resource for resource in aggregate["contained"]
        if resource.get("resourceType") == "DiagnosticReport"
    )
    assert diagnostic_report["meta"]["claims"][DiagnosticReportClaim.CODE_TEXT] == "Informe radiológico"
    assert diagnostic_report["meta"]["codingProposals"][0]["field"] == DiagnosticReportClaim.CODE
    assert diagnostic_report["meta"]["codingProposals"][0]["inputText"] == "Informe radiológico"
    assert _search_fields(diagnostic_report)["diagnosticreport_code-text"] == "Informe radiológico"


def test_generic_concept_derives_a_condition_proposal_from_all_hierarchy_coordinates() -> None:
    csv_text = (
        "API-CONFIG:language=es:subjectKind=animal:dataUse=secondary\n"
        "date,subject_id,section,family,subfamily,concept\n"
        "FECHA,SUJETO,SECCION,FAMILIA,SUBFAMILIA,CONCEPTO\n"
        "2026-03-19,11111111-1111-4111-8111-111111111111,clinica,diagnostico,traumatologia,Fractura de sesamoideo\n"
    )
    with NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        tmp.write(csv_text)
        path = Path(tmp.name)
    try:
        embedded = extract_embedded_api_config(path)
        assert embedded is not None
        records = get_adapter("api-config").read_records(path, _context(embedded["schemaConfig"]))
    finally:
        path.unlink(missing_ok=True)

    assert records[0].coding_inputs == {ConditionClaim.CODE: "Fractura de sesamoideo"}
    assert records[0].flat_claims[ConditionClaim.CODE_TEXT] == "Fractura de sesamoideo"
    result = run_pipeline(records, _context(embedded["schemaConfig"]), NoopCodingAssistant())
    aggregate = result.composition_message["body"]["data"][0]["resource"]
    condition = next(resource for resource in aggregate["contained"] if resource.get("resourceType") == "Condition")
    assert condition["meta"]["codingProposals"][0]["field"] == ConditionClaim.CODE
    assert condition["meta"]["codingProposals"][0]["candidates"] == []
    assert not any(resource.get("resourceType") == "DiagnosticReport" for resource in aggregate["contained"])


def test_generic_vaccine_concept_derives_an_immunization_review_proposal() -> None:
    csv_text = (
        "API-CONFIG:language=es:subjectKind=animal:dataUse=secondary\n"
        "date,subject_id,section,family,subfamily,concept\n"
        "FECHA,SUJETO,SECCION,FAMILIA,SUBFAMILIA,CONCEPTO\n"
        "2026-03-19,11111111-1111-4111-8111-111111111111,clinica,tratamiento,vacunas,Vacuna rabia\n"
    )
    with NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        tmp.write(csv_text)
        path = Path(tmp.name)
    try:
        embedded = extract_embedded_api_config(path)
        assert embedded is not None
        records = get_adapter("api-config").read_records(path, _context(embedded["schemaConfig"]))
    finally:
        path.unlink(missing_ok=True)

    assert records[0].coding_inputs == {ImmunizationClaim.VACCINE_CODE: "Vacuna rabia"}
    assert records[0].flat_claims[ImmunizationClaim.VACCINE_CODE_TEXT] == "Vacuna rabia"
    result = run_pipeline(records, _context(embedded["schemaConfig"]), NoopCodingAssistant())
    aggregate = result.composition_message["body"]["data"][0]["resource"]
    immunization = next(
        resource for resource in aggregate["contained"]
        if resource.get("resourceType") == "Immunization"
    )
    assert immunization["meta"]["claims"][ImmunizationClaim.STATUS] == "completed"
    assert immunization["meta"]["claims"][ImmunizationClaim.DATE] == "2026-03-19T00:00:00Z"
    assert immunization["meta"]["codingProposals"][0]["field"] == ImmunizationClaim.VACCINE_CODE
    assert result.summary["immunizationEntries"] == 1
    assert result.summary["codingProposalEntries"] == 1


def test_allergy_text_derives_an_allergy_intolerance_review_proposal() -> None:
    csv_text = (
        "API-CONFIG:language=es:subjectKind=animal:dataUse=secondary\n"
        "date,subject_id,section,family,subfamily,concept\n"
        "FECHA,SUJETO,SECCION,FAMILIA,SUBFAMILIA,CONCEPTO\n"
        "2026-03-19,11111111-1111-4111-8111-111111111111,clinica,alergias,medicamentos,Alergia a penicilina\n"
    )
    with NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        tmp.write(csv_text)
        path = Path(tmp.name)
    try:
        embedded = extract_embedded_api_config(path)
        assert embedded is not None
        records = get_adapter("api-config").read_records(path, _context(embedded["schemaConfig"]))
    finally:
        path.unlink(missing_ok=True)

    assert records[0].coding_inputs == {AllergyIntoleranceClaim.CODE: "Alergia a penicilina"}
    assert records[0].flat_claims[AllergyIntoleranceClaim.CODE_TEXT] == "Alergia a penicilina"
    result = run_pipeline(records, _context(embedded["schemaConfig"]), NoopCodingAssistant())
    aggregate = result.composition_message["body"]["data"][0]["resource"]
    allergy = next(
        resource for resource in aggregate["contained"]
        if resource.get("resourceType") == "AllergyIntolerance"
    )
    assert allergy["meta"]["claims"][AllergyIntoleranceClaim.VERIFICATION_STATUS] == "unconfirmed"
    assert allergy["meta"]["codingProposals"][0]["field"] == AllergyIntoleranceClaim.CODE
    assert result.summary["allergyIntoleranceEntries"] == 1


def test_explicit_medication_statement_text_becomes_a_reviewable_contained_resource() -> None:
    csv_text = (
        "API-CONFIG:language=es:subjectKind=animal:dataUse=secondary\n"
        f"date,subject_id,section,family,{MedicationStatementClaim.CODE_TEXT}\n"
        "FECHA,SUJETO,SECCION,FAMILIA,TRATAMIENTO\n"
        "2026-03-19,11111111-1111-4111-8111-111111111111,clinica,medicamentos,Trusopt 1 gota 2 veces al día\n"
    )
    with NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        tmp.write(csv_text)
        path = Path(tmp.name)
    try:
        embedded = extract_embedded_api_config(path)
        assert embedded is not None
        records = get_adapter("api-config").read_records(path, _context(embedded["schemaConfig"]))
    finally:
        path.unlink(missing_ok=True)

    assert records[0].coding_inputs == {MedicationStatementClaim.CODE: "Trusopt 1 gota 2 veces al día"}
    result = run_pipeline(records, _context(embedded["schemaConfig"]), NoopCodingAssistant())
    aggregate = result.composition_message["body"]["data"][0]["resource"]
    medication = next(
        resource for resource in aggregate["contained"]
        if resource.get("resourceType") == "MedicationStatement"
    )
    assert medication["meta"]["claims"][MedicationStatementClaim.STATUS] == "unknown"
    assert medication["meta"]["codingProposals"][0]["field"] == MedicationStatementClaim.CODE
    assert result.summary["medicationStatementEntries"] == 1


def test_orphan_procedure_display_is_normalized_to_local_text_for_review() -> None:
    csv_text = (
        "API-CONFIG:language=es:subjectKind=animal:dataUse=secondary\n"
        "date,subject_id,section,family,procedure_code-display\n"
        "FECHA,SUJETO,SECCION,FAMILIA,TRATAMIENTO\n"
        "2026-03-19,11111111-1111-4111-8111-111111111111,clinica,tratamiento,Cura local\n"
    )
    with NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        tmp.write(csv_text)
        path = Path(tmp.name)
    try:
        embedded = extract_embedded_api_config(path)
        assert embedded is not None
        records = get_adapter("api-config").read_records(path, _context(embedded["schemaConfig"]))
    finally:
        path.unlink(missing_ok=True)

    assert records[0].flat_claims[ProcedureClaim.CODE_TEXT] == "Cura local"
    assert ProcedureClaim.CODE_DISPLAY not in records[0].flat_claims
    assert records[0].coding_inputs == {ProcedureClaim.CODE: "Cura local"}

    result = run_pipeline(records, _context(embedded["schemaConfig"]), NoopCodingAssistant())
    aggregate = result.composition_message["body"]["data"][0]["resource"]
    procedure = next(
        resource for resource in aggregate["contained"]
        if resource.get("resourceType") == "Procedure"
    )
    assert procedure["meta"]["claims"][ProcedureClaim.CODE_TEXT] == "Cura local"
    assert ProcedureClaim.CODE_DISPLAY not in procedure["meta"]["claims"]
    assert procedure["meta"]["codingProposals"][0]["field"] == ProcedureClaim.CODE
