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


class RecordingFailingTerminologyClient(RecordingTerminologyClient):
    def search(self, request):
        self.requests.append(request)
        raise RuntimeError("terminology lookup unavailable")


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


def test_lists_up_to_one_thousand_pending_subjects_in_one_authorized_scan() -> None:
    manager, vault, _, _ = _manager()
    vault.put(VAULT_ID, [_research_subject("subject-1", STUDY)], "ResearchSubject")
    body = _search_body()
    body["parameter"].append({"name": "_count", "valueInteger": 1000})

    with patch(
        "adapter_ingestion.service.managers.research_coding_review._enforce_auth_context"
    ):
        result = manager.search_pending(
            tenant_id=TENANT,
            jurisdiction="CA-BC",
            sector="animal-research",
            request=_request(),
            body=body,
        )

    assert result["total"] == 1
    assert len(result["entry"]) == 1


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


def test_searches_and_persists_governed_candidates_for_one_pending_proposal() -> None:
    terminology = RecordingTerminologyClient()
    terminology.search = lambda request: (
        terminology.requests.append(request) or [TerminologyCandidate(
            system="http://hl7.org/fhir/sid/icd-10",
            code="H16.0",
            display="Corneal ulcer",
            source="ICD10",
        )]
    )
    manager, vault, _, _ = _manager(terminology_client=terminology)
    subject = _research_subject("subject-1", STUDY)
    condition = subject["contained"][0]
    condition["resourceType"] = "Condition"
    condition["id"] = "condition-subject-1"
    proposal = condition["meta"]["codingProposals"][0]
    proposal.update({
        "id": "proposal-condition-1",
        "field": "Condition.code",
        "inputText": "ULCERA CORNEAL",
        "language": "es",
        "candidates": [],
    })
    vault.put(VAULT_ID, [subject], "ResearchSubject")
    vault.put(VAULT_ID, [condition], "Condition")

    with patch(
        "adapter_ingestion.service.managers.research_coding_review._enforce_auth_context"
    ):
        result = manager.search_candidates(
            tenant_id=TENANT,
            jurisdiction="CA-BC",
            sector="animal-research",
            request=_request(),
            body={
                "researchStudy": {"reference": STUDY},
                "resourceType": "Condition",
                "resourceId": "condition-subject-1",
                "proposalId": "proposal-condition-1",
                "text": "corneal ulcer",
                "language": "en",
                "sources": ["ICD10"],
            },
        )

    assert terminology.requests[0].resource_type == "Condition"
    assert terminology.requests[0].field == "Condition.code"
    assert terminology.requests[0].text == "corneal ulcer"
    assert terminology.requests[0].language == "en"
    assert terminology.requests[0].sources == ("ICD10",)
    assert result["proposalId"] == "proposal-condition-1"
    assert result["candidates"][0]["code"] == "H16.0"
    stored = vault.get(VAULT_ID, "condition-subject-1", "Condition")
    assert stored["meta"]["codingProposals"][0]["candidates"][0]["code"] == "H16.0"


def test_candidate_search_cannot_retype_the_imported_resource() -> None:
    manager, vault, _, _ = _manager(terminology_client=RecordingTerminologyClient())
    subject = _research_subject("subject-1", STUDY)
    vault.put(VAULT_ID, [subject], "ResearchSubject")

    with patch(
        "adapter_ingestion.service.managers.research_coding_review._enforce_auth_context"
    ):
        try:
            manager.search_candidates(
                tenant_id=TENANT,
                jurisdiction="CA-BC",
                sector="animal-research",
                request=_request(),
                body={
                    "researchStudy": {"reference": STUDY},
                    "resourceType": "Condition",
                    "resourceId": "immunization-subject-1",
                    "proposalId": "proposal-subject-1",
                    "text": "corneal ulcer",
                    "language": "en",
                    "sources": ["ICD10"],
                },
            )
        except Exception as error:
            assert getattr(error, "status_code", None) == 404
        else:
            raise AssertionError("candidate search must keep the imported FHIR resource type")


def test_reclassifies_a_pending_diagnostic_text_before_terminology_search() -> None:
    manager, vault, _, _ = _manager(terminology_client=RecordingTerminologyClient())
    subject = {
        "resourceType": "ResearchSubject",
        "id": "subject-reclassify",
        "meta": {"claims": {"ResearchSubject.study": STUDY}},
        "contained": [
            {
                "resourceType": "Composition",
                "id": "composition-reclassify",
                "meta": {"claims": {
                    "Composition.subject": "ResearchSubject/subject-reclassify",
                    "Composition.section": "http://loinc.org|11450-4",
                    "Composition.entry": "urn:uuid:diagnostic-reclassify",
                    "Composition.relatesto-target": "job-reclassify",
                }},
            },
            {
                "resourceType": "DiagnosticReport",
                "id": "diagnostic-reclassify",
                "meta": {
                    "claims": {"DiagnosticReport.code-text": "fractura de sesamoideo"},
                    "codingProposals": [{
                        "id": "proposal-reclassify",
                        "status": "proposed",
                        "field": "DiagnosticReport.code",
                        "inputText": "fractura de sesamoideo",
                        "language": "es",
                        "rowContext": {"family": "diagnostico"},
                        "candidates": [],
                    }],
                },
            },
        ],
    }
    vault.put(VAULT_ID, [subject], "ResearchSubject")
    vault.put(VAULT_ID, subject["contained"], "Composition")
    vault.put(VAULT_ID, [subject["contained"][1]], "DiagnosticReport")

    with patch(
        "adapter_ingestion.service.managers.research_coding_review._enforce_auth_context"
    ):
        result = manager.reclassify_pending(
            tenant_id=TENANT,
            jurisdiction="CA-BC",
            sector="animal-research",
            request=_request(),
            body={
                "researchStudy": {"reference": STUDY},
                "resourceType": "DiagnosticReport",
                "resourceId": "diagnostic-reclassify",
                "proposalId": "proposal-reclassify",
                "targetResourceType": "Condition",
                "targetField": "Condition.code",
            },
        )

    assert result["resourceType"] == "Condition"
    assert result["field"] == "Condition.code"
    assert result["resourceId"] != "diagnostic-reclassify"
    stored = vault.get(VAULT_ID, "subject-reclassify", "ResearchSubject")
    target = next(item for item in stored["contained"] if item["resourceType"] == "Condition")
    assert target["meta"]["claims"]["Condition.code-text"] == "fractura de sesamoideo"
    assert target["meta"]["codingProposals"][0]["field"] == "Condition.code"
    assert target["meta"]["codingProposals"][0]["candidates"] == []
    assert all(item["resourceType"] != "DiagnosticReport" for item in stored["contained"])
    composition = next(item for item in stored["contained"] if item["resourceType"] == "Composition")
    assert composition["meta"]["claims"]["Composition.entry"] == f"urn:uuid:{result['resourceId']}"
    assert vault.get(VAULT_ID, "diagnostic-reclassify", "DiagnosticReport") is None


def test_prepare_backfills_an_immunization_proposal_from_an_existing_imported_document() -> None:
    terminology = RecordingFailingTerminologyClient()
    manager, vault, _, _ = _manager(terminology_client=terminology)
    subject = {
        "resourceType": "ResearchSubject",
        "id": "subject-vaccine-backfill",
        "meta": {"claims": {
            "ResearchSubject.study": STUDY,
            "Subject.language": "es",
            "Subject.animal-species": "http://hl7.org/fhir/target-species|100000108988",
        }},
        "contained": [
            {
                "resourceType": "Composition",
                "id": "composition-vaccine-backfill",
                "meta": {"claims": {
                    "Composition.subject": "ResearchSubject/subject-vaccine-backfill",
                    "Composition.entry": "urn:uuid:document-vaccine-backfill",
                }},
            },
            {
                "resourceType": "DocumentReference",
                "id": "document-vaccine-backfill",
                "meta": {"claims": {
                    "DocumentReference.subject": "ResearchSubject/subject-vaccine-backfill",
                    "DocumentReference.date": "2025-08-20T18:13:26Z",
                    "DocumentReference.description": "vacuna eurican r lote ho4461 cad 6/9/27",
                    "DocumentReference.language": "es",
                }},
            },
        ],
    }
    vault.put(VAULT_ID, [subject], "ResearchSubject")
    vault.put(VAULT_ID, subject["contained"], "Composition")

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

    assert result["preparedSubjectCount"] == 1
    assert result["proposalCount"] == 1
    assert result["candidateCount"] == 0
    stored = vault.get(VAULT_ID, "subject-vaccine-backfill", "ResearchSubject")
    immunization = next(item for item in stored["contained"] if item["resourceType"] == "Immunization")
    assert immunization["meta"]["claims"]["Immunization.date"] == "2025-08-20T18:13:26Z"
    assert immunization["meta"]["claims"]["Immunization.vaccine-code-text"] == (
        "vacuna eurican r lote ho4461 cad 6/9/27"
    )
    assert immunization["meta"]["codingProposals"][0]["field"] == "Immunization.vaccine-code"
    assert immunization["meta"]["codingProposals"][0]["candidates"] == []
    assert terminology.requests[0].resource_type == "Immunization"
    assert terminology.requests[0].field == "Immunization.vaccine-code"
    composition = next(item for item in stored["contained"] if item["resourceType"] == "Composition")
    assert immunization["id"] in composition["meta"]["claims"]["Composition.entry"]


def test_prepare_does_not_backfill_plans_or_adverse_reaction_mentions_as_completed_immunizations() -> None:
    manager, vault, _, _ = _manager(terminology_client=RecordingFailingTerminologyClient())
    descriptions = (
        "Se desparasita para empezar vacunación",
        "Reacción a la vacuna",
        "Siempre que se la vacuna se pone un antihistamínico",
    )
    subject = {
        "resourceType": "ResearchSubject",
        "id": "subject-vaccine-mentions",
        "meta": {"claims": {
            "ResearchSubject.study": STUDY,
            "Subject.language": "es",
        }},
        "contained": [
            {
                "resourceType": "Composition",
                "id": "composition-vaccine-mentions",
                "meta": {"claims": {
                    "Composition.subject": "ResearchSubject/subject-vaccine-mentions",
                    "Composition.entry": ",".join(
                        f"urn:uuid:document-vaccine-mention-{index}"
                        for index in range(len(descriptions))
                    ),
                }},
            },
            *[
                {
                    "resourceType": "DocumentReference",
                    "id": f"document-vaccine-mention-{index}",
                    "meta": {"claims": {
                        "DocumentReference.subject": "ResearchSubject/subject-vaccine-mentions",
                        "DocumentReference.date": "2025-08-20T18:13:26Z",
                        "DocumentReference.description": description,
                        "DocumentReference.language": "es",
                    }},
                }
                for index, description in enumerate(descriptions)
            ],
        ],
    }
    vault.put(VAULT_ID, [subject], "ResearchSubject")
    vault.put(VAULT_ID, subject["contained"], "Composition")

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
        "preparedSubjectCount": 0,
        "proposalCount": 0,
        "candidateCount": 0,
    }
    stored = vault.get(VAULT_ID, "subject-vaccine-mentions", "ResearchSubject")
    assert all(item["resourceType"] != "Immunization" for item in stored["contained"])


def test_discards_only_pending_drafts_from_the_exact_import_thread() -> None:
    manager, vault, _, _ = _manager()
    subject = _research_subject("subject-discard", STUDY)
    pending = subject["contained"][0]
    subject["contained"] = [
        {
            "resourceType": "Composition",
            "id": "composition-discard",
            "meta": {"claims": {
                "Composition.subject": "ResearchSubject/subject-discard",
                "Composition.section": "http://loinc.org|11369-6",
                "Composition.entry": "urn:uuid:immunization-subject-discard",
                "Composition.relatesto-target": "job-to-discard",
            }},
        },
        pending,
        {
            "resourceType": "Composition",
            "id": "composition-keep",
            "meta": {"claims": {
                "Composition.subject": "ResearchSubject/subject-discard",
                "Composition.section": "http://loinc.org|11450-4",
                "Composition.entry": "urn:uuid:condition-keep",
                "Composition.relatesto-target": "job-to-keep",
            }},
        },
        {
            "resourceType": "Condition",
            "id": "condition-keep",
            "meta": {"claims": {"Condition.code-text": "otitis"}},
        },
    ]
    vault.put(VAULT_ID, [subject], "ResearchSubject")
    for resource in subject["contained"]:
        vault.put(VAULT_ID, [resource], resource["resourceType"])

    with patch(
        "adapter_ingestion.service.managers.research_coding_review._enforce_auth_context"
    ):
        result = manager.discard_pending_import(
            tenant_id=TENANT,
            jurisdiction="CA-BC",
            sector="animal-research",
            request=_request(),
            body={
                "researchStudy": {"reference": STUDY},
                "thid": "job-to-discard",
            },
        )

    assert result == {
        "thid": "job-to-discard",
        "discardedSubjectCount": 1,
        "discardedResourceCount": 2,
    }
    stored = vault.get(VAULT_ID, "subject-discard", "ResearchSubject")
    assert [item["id"] for item in stored["contained"]] == ["composition-keep", "condition-keep"]
    assert vault.get(VAULT_ID, "composition-discard", "Composition") is None
    assert vault.get(VAULT_ID, "immunization-subject-discard", "Immunization") is None
    assert vault.get(VAULT_ID, "composition-keep", "Composition") is not None
    assert vault.get(VAULT_ID, "condition-keep", "Condition") is not None


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
