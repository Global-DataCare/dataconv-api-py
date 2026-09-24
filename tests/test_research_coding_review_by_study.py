# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.
# A study reviewer can recover and resolve durable ResearchSubject proposals
# after the transient conversion Task and upload-response have disappeared.

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from adapter_ingestion.runtime.adapters import (
    InMemoryBlobStore,
    InMemorySearchRepository,
    InMemoryVaultRepository,
)
from adapter_ingestion.service.managers.dependencies import ApiManagerDependencies
from adapter_ingestion.service.managers.research_coding_review import ResearchCodingReviewManager
from adapter_ingestion.ai.terminology import TerminologyCandidate


STUDY = "ResearchStudy/study-durable-review"
OTHER_STUDY = "ResearchStudy/study-not-authorized"
TENANT = "research-tenant"
VAULT_ID = "test__ca-bc__animal-research__research-tenant"


class RecordingFeedbackSink:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def submit(self, event: dict) -> None:
        self.events.append(event)


class RecordingTerminologyClient:
    def __init__(self) -> None:
        self.requests = []

    def search(self, request):
        self.requests.append(request)
        return [TerminologyCandidate(
            system="http://snomed.info/sct",
            code="3135009",
            display="Otitis media",
            source="SNOMED CT",
        )]


def _research_subject(subject_id: str, study: str, *, proposal_status: str = "proposed") -> dict:
    return {
        "resourceType": "ResearchSubject",
        "id": subject_id,
        "meta": {"claims": {
            "ResearchSubject.status": "candidate",
            "ResearchSubject.study": study,
        }},
        "contained": [{
            "resourceType": "Immunization",
            "id": f"immunization-{subject_id}",
            "meta": {
                "claims": {"Immunization.vaccine-code-text": "rabia"},
                "codingProposals": [{
                    "id": f"proposal-{subject_id}",
                    "status": proposal_status,
                    "field": "Immunization.vaccine-code",
                    "inputText": "rabia",
                    "rowContext": {"rowNumber": subject_id},
                    "candidates": [{
                        "id": f"candidate-{subject_id}",
                        "system": "http://www.whocc.no/atcvet",
                        "code": "QI07AA02",
                        "display": "Rabies virus, inactivated",
                    }],
                }],
            },
        }],
    }


def _manager(*, terminology_client=None) -> tuple[ResearchCodingReviewManager, InMemoryVaultRepository, InMemorySearchRepository, RecordingFeedbackSink]:
    vault = InMemoryVaultRepository()
    search = InMemorySearchRepository()
    feedback = RecordingFeedbackSink()
    deps = ApiManagerDependencies(
        settings=SimpleNamespace(
            network_mode="test",
            demo_mode=False,
            supported_jurisdictions=("*",),
            supported_sectors=("*",),
        ),
        control_plane=SimpleNamespace(),
        blob_store=InMemoryBlobStore(),
        vault_repo=vault,
        search_repo=search,
        config_create_responses={},
        coding_feedback_sink=feedback,
        terminology_client=terminology_client,
    )
    return ResearchCodingReviewManager(deps), vault, search, feedback


def _request() -> SimpleNamespace:
    return SimpleNamespace(headers={"authorization": "Bearer study-token"})


def _search_body(study: str = STUDY) -> dict:
    return {
        "resourceType": "Parameters",
        "parameter": [{"name": "study", "valueReference": {"reference": study}}],
    }


def test_lists_pending_proposals_from_durable_research_subjects_without_a_job() -> None:
    manager, vault, _, _ = _manager()
    pending = _research_subject("subject-1", STUDY)
    already_reviewed = _research_subject("subject-2", STUDY, proposal_status="accepted")
    another_study = _research_subject("subject-3", OTHER_STUDY)
    for subject in (pending, already_reviewed, another_study):
        vault.put(VAULT_ID, [subject], "ResearchSubject")

    with patch(
        "adapter_ingestion.service.managers.research_coding_review._enforce_auth_context"
    ) as enforce:
        result = manager.search_pending(
            tenant_id=TENANT,
            jurisdiction="CA-BC",
            sector="animal-research",
            request=_request(),
            body=_search_body(),
        )

    assert result["resourceType"] == "Bundle"
    assert result["type"] == "searchset"
    assert result["total"] == 1
    resource = result["entry"][0]["resource"]
    assert resource["id"] == "subject-1"
    assert resource["contained"][0]["meta"]["codingProposals"][0]["status"] == "proposed"
    enforce.assert_called_once()
    assert enforce.call_args.kwargs["required_scopes"] == {"dataconv.review"}
    assert enforce.call_args.kwargs["expected_organization"] == TENANT
    assert enforce.call_args.kwargs["expected_research_study"] == STUDY


def test_prepares_missing_legacy_code_text_for_review_without_reimporting() -> None:
    terminology = RecordingTerminologyClient()
    manager, vault, _, _ = _manager(terminology_client=terminology)
    subject = {
        "resourceType": "ResearchSubject",
        "id": "subject-legacy",
        "meta": {"claims": {
            "ResearchSubject.study": STUDY,
            "Subject.language": "es",
            "Subject.animal-species": "canine",
        }},
        "contained": [{
            "resourceType": "DiagnosticReport",
            "id": "diagnostic-legacy",
            "meta": {"claims": {"DiagnosticReport.code-text": "otitis"}},
        }],
    }
    vault.put(VAULT_ID, [subject], "ResearchSubject")
    vault.put(VAULT_ID, [subject["contained"][0]], "DiagnosticReport")

    with patch(
        "adapter_ingestion.service.managers.research_coding_review._enforce_auth_context"
    ):
        result = manager.prepare_pending(
            tenant_id=TENANT,
            jurisdiction="CA-BC",
            sector="animal-research",
            request=_request(),
            body=_search_body(),
        )

    assert result == {
        "preparedSubjectCount": 1,
        "proposalCount": 1,
        "candidateCount": 1,
    }
    stored = vault.get(VAULT_ID, "subject-legacy", "ResearchSubject")
    proposal = stored["contained"][0]["meta"]["codingProposals"][0]
    assert proposal["field"] == "DiagnosticReport.code"
    assert proposal["inputText"] == "otitis"
    assert proposal["candidates"][0]["code"] == "3135009"
    assert terminology.requests[0].language == "es"


def test_search_uses_the_latest_canonical_contained_resource_state() -> None:
    manager, vault, _, _ = _manager()
    stale_subject = _research_subject("subject-1", STUDY)
    current_contained = _research_subject(
        "subject-1", STUDY, proposal_status="accepted"
    )["contained"][0]
    vault.put(VAULT_ID, [stale_subject], "ResearchSubject")
    vault.put(VAULT_ID, [current_contained], "Immunization")

    with patch(
        "adapter_ingestion.service.managers.research_coding_review._enforce_auth_context"
    ):
        result = manager.search_pending(
            tenant_id=TENANT,
            jurisdiction="CA-BC",
            sector="animal-research",
            request=_request(),
            body=_search_body(),
        )

    assert result["total"] == 0


def test_applies_review_to_durable_subject_and_promotes_it_without_conversion_task() -> None:
    manager, vault, search, feedback = _manager()
    subject = _research_subject("subject-1", STUDY)
    contained = subject["contained"][0]
    vault.put(VAULT_ID, [subject], "ResearchSubject")
    vault.put(VAULT_ID, [contained], "Immunization")

    with patch(
        "adapter_ingestion.service.managers.research_coding_review._enforce_auth_context"
    ):
        result = manager.apply_reviews(
            tenant_id=TENANT,
            jurisdiction="CA-BC",
            sector="animal-research",
            request=_request(),
            body={
                "researchStudy": {"reference": STUDY},
                "codingReviews": [{
                    "resourceType": "Immunization",
                    "resourceId": "immunization-subject-1",
                    "proposalId": "proposal-subject-1",
                    "selectedCandidateId": "candidate-subject-1",
                    "reason": "Confirmed against the source record",
                }],
            },
        )

    assert result["status"] == "success"
    assert result["reviewedProposalCount"] == 1
    assert result["promotedSubjectCount"] == 1
    stored = vault.get(VAULT_ID, "subject-1", "ResearchSubject")
    proposal = stored["contained"][0]["meta"]["codingProposals"][0]
    claims = stored["contained"][0]["meta"]["claims"]
    assert proposal["status"] == "accepted"
    assert claims["Immunization.vaccine-code"] == "http://www.whocc.no/atcvet|QI07AA02"
    assert claims["Immunization.userSelected"] == "true"
    assert vault.get(VAULT_ID, "immunization-subject-1", "Immunization") == stored["contained"][0]
    assert search.search(
        vault_id=VAULT_ID,
        resource_type="ResearchSubject",
        search_params={"study": STUDY},
    ) == [stored]
    assert feedback.events[0]["reason"] == "Confirmed against the source record"


def test_rejects_review_resource_that_is_not_in_the_authorized_study() -> None:
    manager, vault, _, _ = _manager()
    subject = _research_subject("subject-1", OTHER_STUDY)
    vault.put(VAULT_ID, [subject], "ResearchSubject")

    with patch(
        "adapter_ingestion.service.managers.research_coding_review._enforce_auth_context"
    ):
        try:
            manager.apply_reviews(
                tenant_id=TENANT,
                jurisdiction="CA-BC",
                sector="animal-research",
                request=_request(),
                body={
                    "researchStudy": {"reference": STUDY},
                    "codingReviews": [{
                        "resourceType": "Immunization",
                        "resourceId": "immunization-subject-1",
                        "proposalId": "proposal-subject-1",
                        "selectedCandidateId": "candidate-subject-1",
                    }],
                },
            )
        except Exception as error:
            assert getattr(error, "status_code", None) == 404
        else:
            raise AssertionError("cross-study review must fail")


def test_validates_the_complete_review_set_before_mutating_any_draft() -> None:
    manager, vault, _, feedback = _manager()
    subject = _research_subject("subject-1", STUDY)
    vault.put(VAULT_ID, [subject], "ResearchSubject")

    with patch(
        "adapter_ingestion.service.managers.research_coding_review._enforce_auth_context"
    ):
        try:
            manager.apply_reviews(
                tenant_id=TENANT,
                jurisdiction="CA-BC",
                sector="animal-research",
                request=_request(),
                body={
                    "researchStudy": {"reference": STUDY},
                    "codingReviews": [
                        {
                            "resourceType": "Immunization",
                            "resourceId": "immunization-subject-1",
                            "proposalId": "proposal-subject-1",
                            "selectedCandidateId": "candidate-subject-1",
                        },
                        {
                            "resourceType": "Observation",
                            "resourceId": "missing-resource",
                            "proposalId": "missing-proposal",
                            "selectedCandidateId": "missing-candidate",
                        },
                    ],
                },
            )
        except Exception as error:
            assert getattr(error, "status_code", None) == 404
        else:
            raise AssertionError("an invalid review set must fail atomically")

    stored = vault.get(VAULT_ID, "subject-1", "ResearchSubject")
    assert stored["contained"][0]["meta"]["codingProposals"][0]["status"] == "proposed"
    assert feedback.events == []
