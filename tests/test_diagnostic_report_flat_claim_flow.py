# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from gdc_data_utils import ConditionClaim, DiagnosticReportClaim

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
        f"date,subject_id,section,family,coding-input:{ConditionClaim.CODE}\n"
        "FECHA,SUJETO,SECCION,FAMILIA,DIAGNOSTICO\n"
        "2026-03-19,11111111-1111-4111-8111-111111111111,clinica,diagnostico,Otitis externa\n"
    )
    with NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        tmp.write(csv_text)
        path = Path(tmp.name)
    try:
        embedded = extract_embedded_api_config(path)
        assert embedded is not None
        assert embedded["schemaConfig"]["fieldMap"][f"coding-input:{ConditionClaim.CODE}"] == "DIAGNOSTICO"

        records = get_adapter("api-config").read_records(
            path,
            _context(embedded["schemaConfig"]),
        )
    finally:
        path.unlink(missing_ok=True)

    assert records[0].flat_claims == {}
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
    assert _search_fields(diagnostic_report)["diagnosticreport_code-text"] == "Informe radiológico"
