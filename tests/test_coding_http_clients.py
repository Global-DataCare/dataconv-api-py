# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.
# 1. DataConv requests governed candidates from the terminology JSON:API endpoint.
# 2. It sends the complete closed candidate set to the coding model for ranking.
# 3. The model can rank only candidate identifiers supplied by DataConv.
# 4. Human review feedback is sent as a separate JSON:API resource.

from __future__ import annotations

from dataclasses import dataclass, field

from adapter_ingestion.ai.http import HttpCodingModelClient, HttpTerminologyClient
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
