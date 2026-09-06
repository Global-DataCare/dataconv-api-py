# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.
# Research uploads, review lookup and public ResearchSubject search retain one
# stable FHIR ResearchStudy reference without treating it as authorization.

from __future__ import annotations

from types import SimpleNamespace
import json

import pytest

from adapter_ingestion.runtime import JobRequest, PreconversionControlPlane
from adapter_ingestion.runtime.adapters import (
    InMemoryConfigStore,
    InMemoryJobQueue,
    InMemoryJobStore,
    InMemorySearchRepository,
    InMemoryVaultRepository,
)
from adapter_ingestion.runtime.adapters.filesystem import _dict_to_job as filesystem_dict_to_job
from adapter_ingestion.runtime.adapters.filesystem import _job_to_dict as filesystem_job_to_dict
from adapter_ingestion.runtime.adapters.gcp import _dict_to_job as firestore_dict_to_job
from adapter_ingestion.runtime.adapters.gcp import _job_to_dict as firestore_job_to_dict
from adapter_ingestion.service.research_drafts import persist_research_drafts
from adapter_ingestion.service.research_study import require_research_study_reference


RESEARCH_STUDY_REFERENCE = "ResearchStudy/study-2026-01"


def _control_plane() -> PreconversionControlPlane:
    return PreconversionControlPlane(
        config_store=InMemoryConfigStore(),
        job_store=InMemoryJobStore(),
        job_queue=InMemoryJobQueue(),
    )


def _job_request(*, research_study_reference: str = RESEARCH_STUDY_REFERENCE) -> JobRequest:
    return JobRequest(
        alternate_name="research-tenant",
        manufacturer="source-system",
        sector="onehealth-research",
        country="CA-BC",
        input_ref="mem://uploads/research.xlsx",
        requested_by="did:web:professional.example:employee:reviewer",
        thid="research-conversion-1",
        research_study_reference=research_study_reference,
    )


def test_requires_a_literal_fhir_research_study_reference_object() -> None:
    assert require_research_study_reference({
        "body": {"researchStudy": {"reference": RESEARCH_STUDY_REFERENCE}}
    }) == RESEARCH_STUDY_REFERENCE
    assert require_research_study_reference({
        "researchStudy": json.dumps({"reference": RESEARCH_STUDY_REFERENCE})
    }) == RESEARCH_STUDY_REFERENCE

    with pytest.raises(ValueError, match="researchStudy.reference is required"):
        require_research_study_reference({"body": {}})
    with pytest.raises(ValueError, match="FHIR Reference object"):
        require_research_study_reference({"body": {"researchStudy": RESEARCH_STUDY_REFERENCE}})
    with pytest.raises(ValueError, match="FHIR ResearchStudy reference"):
        require_research_study_reference({"body": {"researchStudy": {"reference": "Patient/not-a-study"}}})


def test_control_plane_get_and_list_are_filterable_by_study_reference() -> None:
    control = _control_plane()
    first = control.submit_job(_job_request())
    second = control.submit_job(_job_request(research_study_reference="ResearchStudy/study-2026-02"))

    assert control.get_job_by_thid(first.thid, research_study_reference=RESEARCH_STUDY_REFERENCE) == first
    assert control.get_job_by_thid(first.thid, research_study_reference="ResearchStudy/study-2026-02") is None
    assert control.list_jobs(research_study_reference=RESEARCH_STUDY_REFERENCE) == [first]
    assert control.list_jobs(research_study_reference="ResearchStudy/study-2026-02") == [second]


def test_filesystem_and_firestore_job_documents_roundtrip_the_study_reference() -> None:
    job = _control_plane().submit_job(_job_request())

    filesystem_document = filesystem_job_to_dict(job)
    firestore_document = firestore_job_to_dict(job)

    assert filesystem_document["request"]["researchStudyReference"] == RESEARCH_STUDY_REFERENCE
    assert firestore_document["request"]["researchStudyReference"] == RESEARCH_STUDY_REFERENCE
    assert filesystem_dict_to_job(filesystem_document).request.research_study_reference == RESEARCH_STUDY_REFERENCE
    assert firestore_dict_to_job(firestore_document).request.research_study_reference == RESEARCH_STUDY_REFERENCE

    filesystem_document["request"].pop("researchStudyReference")
    firestore_document["request"].pop("researchStudyReference")
    assert filesystem_dict_to_job(filesystem_document).request.research_study_reference == ""
    assert firestore_dict_to_job(firestore_document).request.research_study_reference == ""


def test_drafts_and_searchable_research_subjects_retain_the_standard_study_claim() -> None:
    control = _control_plane()
    job = control.submit_job(_job_request())
    vault = InMemoryVaultRepository()
    composition_message = {
        "body": {
            "data": [{
                "resource": {
                    "resourceType": "ResearchSubject",
                    "id": "subject-1",
                    "meta": {"claims": {"ResearchSubject.status": "candidate"}},
                }
            }]
        }
    }

    assert persist_research_drafts(
        vault_repo=vault,
        job=job,
        network_kind="test",
        jurisdiction="CA-BC",
        composition_message=composition_message,
    ) == 1

    vault_id = "test__ca-bc__onehealth-research__research-tenant"
    stored = vault.get(vault_id, "subject-1", "ResearchSubject")
    assert stored is not None
    assert stored["meta"]["claims"]["ResearchSubject.study"] == RESEARCH_STUDY_REFERENCE

    search = InMemorySearchRepository()
    assert search.upsert(vault_id=vault_id, resource_type="ResearchSubject", resource=stored)
    assert search.search(
        vault_id=vault_id,
        resource_type="ResearchSubject",
        search_params={"study": RESEARCH_STUDY_REFERENCE},
    ) == [stored]
    assert search.search(
        vault_id=vault_id,
        resource_type="ResearchSubject",
        search_params={"study": "ResearchStudy/another-study"},
    ) == []


def test_study_reference_is_context_not_local_authorization() -> None:
    request = _job_request()
    assert not hasattr(request, "consent")
    assert not hasattr(request, "smart_scope")
    assert request.research_study_reference == RESEARCH_STUDY_REFERENCE
