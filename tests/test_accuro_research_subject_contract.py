# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.

from __future__ import annotations

from types import SimpleNamespace

from adapter_ingestion.ai.base import NoopCodingAssistant
from adapter_ingestion.models import AdapterContext, CanonicalRecord
from adapter_ingestion.pipeline import run_pipeline
from adapter_ingestion.runtime.adapters import InMemorySearchRepository
from adapter_ingestion.service.managers.conversion_search import ConversionSearchManager


def test_secondary_use_pipeline_exposes_research_subject_as_the_twin_aggregate() -> None:
    context = AdapterContext(
        manufacturer="accuro",
        tenant_id="clinic-a",
        jurisdiction="ES",
        sector="onehealth-research",
        issuer_did="did:web:issuer.example",
        audience_did="did:web:audience.example",
        subject_did_prefix="urn:uuid",
        subject_kind="animal",
        strict_species_mapping=False,
        data_use="secondary",
    )
    record = CanonicalRecord(
        source_row_number=4,
        source_id="source-row-1",
        timestamp="2026-03-19T15:00:00Z",
        subject_id="urn:uuid:11111111-1111-4111-8111-111111111111",
        section="clinical",
        family="encounter",
        subfamily="consultation",
        concept="follow-up",
        composition_section="clinical:encounter",
        document_type_code="urn:accuro:clinical:encounter:consultation",
    )

    result = run_pipeline([record], context, NoopCodingAssistant())

    resource = result.composition_message["body"]["data"][0]["resource"]
    assert resource["resourceType"] == "ResearchSubject"
    assert resource["meta"]["claims"]["ResearchSubject.identifier"] == record.subject_id
    assert resource["meta"]["claims"]["ResearchSubject.status"] == "candidate"
    assert resource["composition"]["resourceType"] == "Composition"
    assert result.summary["researchSubjectEntries"] == 1
    assert result.summary["patientEntries"] == 0


def test_research_subject_search_accepts_fhir_parameters_and_returns_searchset_bundle() -> None:
    subject_identifier = "urn:uuid:11111111-1111-4111-8111-111111111111"
    repository = InMemorySearchRepository()
    repository.upsert(
        vault_id="test__es__onehealth-research__clinic-a",
        resource_type="ResearchSubject",
        resource={
            "resourceType": "ResearchSubject",
            "id": subject_identifier.removeprefix("urn:uuid:"),
            "meta": {
                "claims": {
                    "ResearchSubject.identifier": subject_identifier,
                    "ResearchSubject.status": "candidate",
                }
            },
        },
    )
    manager = ConversionSearchManager(
        SimpleNamespace(
            settings=SimpleNamespace(demo_mode=True, network_mode="test"),
            search_repo=repository,
        )
    )

    result = manager.handle(
        tenant_id="clinic-a",
        jurisdiction="ES",
        sector="onehealth-research",
        resource_type="ResearchSubject",
        response=SimpleNamespace(),
        request=SimpleNamespace(headers={}, query_params={}),
        body={
            "resourceType": "Parameters",
            "parameter": [
                {"name": "identifier", "valueUri": subject_identifier},
                {"name": "status", "valueCode": "candidate"},
                {"name": "_count", "valueInteger": 10},
            ],
        },
    )

    assert result["resourceType"] == "Bundle"
    assert result["type"] == "searchset"
    assert result["total"] == 1
    assert result["entry"][0]["resource"]["meta"]["claims"]["ResearchSubject.identifier"] == subject_identifier
