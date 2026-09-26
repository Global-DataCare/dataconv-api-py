# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.
# 1. DataConv requests governed candidates from the terminology JSON:API endpoint.
# 2. It sends the complete closed candidate set to the coding model for ranking.
# 3. The model can rank only candidate identifiers supplied by DataConv.
# 4. Human review feedback is sent as a separate JSON:API resource.

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse
import pytest

from adapter_ingestion.ai.http import (
    TERMINOLOGY_QUERY_TEXT_MIN_LENGTH,
    TERMINOLOGY_QUERY_TEXT_MAX_LENGTH,
    HttpCodingModelClient,
    HttpReviewedTerminologySink,
    HttpTerminologyClient,
)
from adapter_ingestion.ai.terminology import CodingRankRequest, TerminologyCandidate, TerminologySearchRequest


@dataclass
class RecordingTransport:
    responses: list[dict]
    calls: list[dict] = field(default_factory=list)

    def request(self, *, method: str, url: str, headers: dict[str, str], body: dict | None = None) -> dict:
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body})
        return self.responses.pop(0)


def test_terminology_jsonapi_response_preserves_every_code_and_system() -> None:
    transport = RecordingTransport(responses=[{
        "jsonapi": {"version": "1.1"},
        "data": [
            {
                "type": "terminology-system",
                "id": "http://snomed.info/sct",
                "attributes": {"3135009": "Otitis media", "129127001": "Otitis externa"},
                "meta": {"language": "en", "sources": ["SNOMED_GPS"]},
            },
            {
                "type": "terminology-system",
                "id": "http://hl7.org/fhir/sid/icd-10",
                "attributes": {"H66.9": "Otitis media, unspecified"},
                "meta": {"language": "en", "sources": ["ICD10"]},
            },
        ],
    }])
    client = HttpTerminologyClient(base_url="https://terminology.example", token="secret", transport=transport)

    candidates = client.search(TerminologySearchRequest(
        text="otitis", language="es-ES", fhir_version="R4", sector="animal-care",
        jurisdiction="CA-BC", resource_type="Condition", field="Condition.code",
    ))

    assert [(item.system, item.code, item.display) for item in candidates] == [
        ("http://snomed.info/sct", "3135009", "Otitis media"),
        ("http://snomed.info/sct", "129127001", "Otitis externa"),
        ("http://hl7.org/fhir/sid/icd-10", "H66.9", "Otitis media, unspecified"),
    ]
    assert "resourceType=Condition" in transport.calls[0]["url"]
    assert transport.calls[0]["headers"]["authorization"] == "Bearer secret"


def test_terminology_query_bounds_long_clinical_text_without_changing_the_source_request() -> None:
    transport = RecordingTransport(responses=[{"jsonapi": {"version": "1.1"}, "data": []}])
    client = HttpTerminologyClient(base_url="https://terminology.example", transport=transport)
    source_text = "x" * (TERMINOLOGY_QUERY_TEXT_MAX_LENGTH + 22)
    request = TerminologySearchRequest(
        text=source_text, language="es", fhir_version="R4", sector="animal-care",
        jurisdiction="CA-BC", resource_type="Procedure", field="Procedure.code",
    )

    client.search(request)

    sent_text = parse_qs(urlparse(transport.calls[0]["url"]).query)["text"][0]
    assert sent_text == source_text[:TERMINOLOGY_QUERY_TEXT_MAX_LENGTH]
    assert request.text == source_text


def test_terminology_query_forwards_the_exact_governed_source_selection() -> None:
    transport = RecordingTransport(responses=[{"jsonapi": {"version": "1.1"}, "data": []}])
    client = HttpTerminologyClient(base_url="https://terminology.example", transport=transport)

    client.search(TerminologySearchRequest(
        text="corneal ulcer", language="en", fhir_version="R4", sector="animal-care",
        jurisdiction="CA-BC", resource_type="Condition", field="Condition.code",
        sources=("ICD10", "SNOMED_CT"),
    ))

    query = parse_qs(urlparse(transport.calls[0]["url"]).query)
    assert query["source"] == ["ICD10", "SNOMED_CT"]


def test_terminology_query_skips_text_shorter_than_the_service_contract() -> None:
    transport = RecordingTransport(responses=[])
    client = HttpTerminologyClient(base_url="https://terminology.example", transport=transport)

    candidates = client.search(TerminologySearchRequest(
        text="x" * (TERMINOLOGY_QUERY_TEXT_MIN_LENGTH - 1), language="es", fhir_version="R4",
        sector="animal-care", jurisdiction="CA-BC", resource_type="Procedure", field="Procedure.code",
    ))

    assert candidates == []
    assert transport.calls == []


def test_model_ranking_is_bounded_to_supplied_candidate_ids() -> None:
    candidates = (
        TerminologyCandidate("http://snomed.info/sct", "3135009", "Otitis media", "SNOMED_GPS", "Condition", "Condition.code", "one"),
        TerminologyCandidate("http://snomed.info/sct", "129127001", "Otitis externa", "SNOMED_GPS", "Condition", "Condition.code", "two"),
    )
    transport = RecordingTransport(responses=[{
        "data": [{
            "type": "coding-ranking",
            "attributes": {"ranking": [
                {"candidateId": "two", "recommendationPercent": 65, "evidence": "external canal finding"},
                {"candidateId": "invented", "recommendationPercent": 99, "evidence": "not allowed"},
                {"candidateId": "one", "recommendationPercent": 35, "evidence": "recurrent signs"},
            ]},
        }],
    }])
    client = HttpCodingModelClient(base_url="https://coding.example", token="model-secret", model="gemma-coding", transport=transport)

    ranked = client.rank(CodingRankRequest(
        text="otitis", language="es-ES", sector="animal-care", jurisdiction="CA-BC",
        subject_kind="animal", resource_type="Condition", field="Condition.code",
        row_context={"symptoms": "external canal finding"}, candidates=candidates,
    ))

    assert [item.candidate_id for item in ranked] == ["two", "one"]
    assert [item.recommendation_percent for item in ranked] == [65.0, 35.0]
    sent = transport.calls[0]["body"]["data"][0]["attributes"]
    assert [item["id"] for item in sent["candidates"]] == ["one", "two"]
    assert sent["model"] == "gemma-coding"


def test_review_feedback_uses_a_separate_endpoint() -> None:
    transport = RecordingTransport(responses=[{"meta": {"accepted": True}}])
    client = HttpCodingModelClient(base_url="https://coding.example", token="model-secret", transport=transport)

    client.submit({"proposalId": "proposal-1", "selectedCandidateId": "two", "reason": "otoscopy"})

    assert transport.calls[0]["method"] == "POST"
    assert transport.calls[0]["url"] == "https://coding.example/v1/coding/feedback"
    assert transport.calls[0]["body"]["data"][0]["type"] == "coding-review-feedback"


def test_professional_review_populates_the_channel_neutral_terminology_store() -> None:
    transport = RecordingTransport(responses=[{"data": {"id": "mapping-1"}}])
    sink = HttpReviewedTerminologySink(base_url="https://terminology.example", token="term-secret", transport=transport)

    sink.submit({
        "proposalId": "proposal-123456789",
        "inputText": "otitis",
        "language": "es-ES",
        "fhirVersion": "R4",
        "sector": "animal-care",
        "jurisdiction": "CA-BC",
        "resourceType": "Condition",
        "field": "Condition.code",
        "candidates": [
            {"id": "one", "source": "SNOMED_GPS", "system": "http://snomed.info/sct", "code": "3135009", "display": "Otitis media"},
            {"id": "two", "source": "SNOMED_GPS", "system": "http://snomed.info/sct", "code": "129127001", "display": "Otitis externa"},
        ],
        "selectedCandidateId": "two",
        "reviewerSubject": "did:web:reviewer.example",
    })

    call = transport.calls[0]
    assert call["url"] == "https://terminology.example/v1/terminology/reviews"
    assert call["headers"]["authorization"] == "Bearer term-secret"
    assert call["body"]["reviewerKind"] == "professional"
    assert call["body"]["reviewState"] == "approved"
    assert call["body"]["chosen"] == {"system": "http://snomed.info/sct", "code": "129127001"}
    assert call["body"]["approvalEvidence"] == "dataconv-review:proposal-123456789"
    assert "reviewerSubject" not in call["body"]
    assert call["body"]["terminologyVersion"].startswith("candidate-set-sha256:")


def test_reviewed_terminology_sink_rejects_a_selection_outside_its_candidate_set() -> None:
    transport = RecordingTransport(responses=[])
    sink = HttpReviewedTerminologySink(base_url="https://terminology.example", transport=transport)
    with pytest.raises(ValueError, match="not part of the review"):
        sink.submit({
            "proposalId": "proposal-123456789",
            "inputText": "otitis", "language": "es-ES", "fhirVersion": "R4",
            "sector": "animal-care", "jurisdiction": "CA-BC",
            "resourceType": "Condition", "field": "Condition.code",
            "candidates": [{"id": "one", "source": "SNOMED_GPS", "system": "http://snomed.info/sct", "code": "3135009", "display": "Otitis media"}],
            "selectedCandidateId": "invented",
        })
    assert transport.calls == []


def test_reviewed_terminology_sink_keeps_legacy_context_free_drafts_promotable() -> None:
    transport = RecordingTransport(responses=[])
    sink = HttpReviewedTerminologySink(base_url="https://terminology.example", transport=transport)
    sink.submit({"proposalId": "legacy-proposal", "selectedCandidateId": "one", "candidates": []})
    assert transport.calls == []
