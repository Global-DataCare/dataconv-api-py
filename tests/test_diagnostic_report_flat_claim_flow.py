# Flow contract: preserve flat FHIR-like claims and map FHIR search syntax only at the storage boundary.

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from types import SimpleNamespace

from gdc_data_utils import DiagnosticReportClaim

from adapter_ingestion.ai.base import NoopCodingAssistant
from adapter_ingestion.manufacturers.registry import get_adapter
from adapter_ingestion.models import AdapterContext
from adapter_ingestion.pipeline import run_pipeline
from adapter_ingestion.runtime.adapters import InMemorySearchRepository
from adapter_ingestion.runtime.adapters.search import _search_fields
from adapter_ingestion.service.api_config import extract_embedded_api_config
from adapter_ingestion.service.managers.conversion_search import ConversionSearchManager


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


def test_api_config_materializes_and_searches_diagnostic_report_code_text() -> None:
    csv_text = (
        "API-CONFIG:language=es:subjectKind=animal:dataUse=secondary\n"
        "date,subject_id,section,family,DiagnosticReport.code-text\n"
        "FECHA,SUJETO,SECCION,FAMILIA,DIAGNOSTICO\n"
        "2026-03-19,11111111-1111-4111-8111-111111111111,clinica,diagnostico,Otitis externa\n"
    )
    with NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        tmp.write(csv_text)
        path = Path(tmp.name)
    try:
        embedded = extract_embedded_api_config(path)
        assert embedded is not None
        assert embedded["schemaConfig"]["fieldMap"][DiagnosticReportClaim.CODE_TEXT] == "DIAGNOSTICO"

        records = get_adapter("api-config").read_records(
            path,
            _context(embedded["schemaConfig"]),
        )
    finally:
        path.unlink(missing_ok=True)

    assert records[0].flat_claims == {
        DiagnosticReportClaim.CODE_TEXT: "Otitis externa",
    }

    result = run_pipeline(records, _context(embedded["schemaConfig"]), NoopCodingAssistant())
    aggregate = result.composition_message["body"]["data"][0]["resource"]
    diagnostic_report = next(
        resource
        for resource in aggregate["contained"]
        if resource.get("resourceType") == "DiagnosticReport"
    )
    assert diagnostic_report["meta"]["claims"] == {
        "@context": "org.hl7.fhir.api",
        DiagnosticReportClaim.CODE_TEXT: "Otitis externa",
    }
    assert "DiagnosticReport.code-display" not in diagnostic_report["meta"]["claims"]

    physical_fields = _search_fields(diagnostic_report)
    assert physical_fields["diagnosticreport_code-text"] == "Otitis externa"
    assert "diagnosticreport_code_text" not in physical_fields

    repository = InMemorySearchRepository()
    repository.upsert(
        vault_id="test__es__onehealth-research__clinic-a",
        resource_type="DiagnosticReport",
        resource=diagnostic_report,
    )
    matches = repository.search(
        vault_id="test__es__onehealth-research__clinic-a",
        resource_type="DiagnosticReport",
        search_params={"code:text": "titis ext"},
    )
    assert [resource["id"] for resource in matches] == [diagnostic_report["id"]]

    bundle = ConversionSearchManager(
        SimpleNamespace(
            settings=SimpleNamespace(demo_mode=True, network_mode="test"),
            search_repo=repository,
        )
    ).handle(
        tenant_id="clinic-a",
        jurisdiction="ES",
        sector="onehealth-research",
        resource_type="DiagnosticReport",
        response=SimpleNamespace(),
        request=SimpleNamespace(headers={}, query_params={}),
        body={
            "resourceType": "Parameters",
            "parameter": [
                {"name": "code:text", "valueString": "titis ext"},
            ],
        },
    )
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "searchset"
    assert bundle["total"] == 1
