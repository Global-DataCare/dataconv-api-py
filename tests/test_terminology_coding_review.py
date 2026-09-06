# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.
# 1. DataConv sends the de-identified row context and every governed terminology candidate to the ranker.
# 2. Every candidate remains available for human choice; the model only supplies a recommendation score.
# 3. A draft carries proposals outside authoritative flat claims.
# 4. Human confirmation writes only the selected code plus English display and emits durable feedback.

from __future__ import annotations

from dataclasses import dataclass, field

from gdc_data_utils import ConditionClaim

from adapter_ingestion.ai.base import CodingSuggestion
from adapter_ingestion.ai.terminology import (
    CodingRankRequest,
    TerminologyCandidate,
    TerminologyCodingAssistant,
    TerminologySearchRequest,
)
from adapter_ingestion.models import AdapterContext, CanonicalRecord
from adapter_ingestion.pipeline import run_pipeline
from adapter_ingestion.runtime.adapters import InMemorySearchRepository
from adapter_ingestion.service.coding_review import apply_coding_reviews


@dataclass
class FakeTerminologyClient:
    requests: list[TerminologySearchRequest] = field(default_factory=list)

    def search(self, request: TerminologySearchRequest) -> list[TerminologyCandidate]:
        self.requests.append(request)
        return [
            TerminologyCandidate(
                system="http://snomed.info/sct",
                code="3135009",
                display="Otitis media",
                source="SNOMED_GPS",
            ),
            TerminologyCandidate(
                system="http://snomed.info/sct",
                code="129127001",
                display="Otitis externa",
                source="SNOMED_GPS",
            ),
        ]


@dataclass
class FakeRanker:
    requests: list[CodingRankRequest] = field(default_factory=list)

    def rank(self, request: CodingRankRequest) -> list[CodingSuggestion]:
        self.requests.append(request)
        first, second = request.candidates
        return [
            CodingSuggestion.from_candidate(first, recommendation_percent=56.0, evidence="recurrent ear discharge"),
            CodingSuggestion.from_candidate(second, recommendation_percent=44.0, evidence="ear canal signs"),
        ]


@dataclass
class RecordingFeedbackSink:
    events: list[dict] = field(default_factory=list)

    def submit(self, event: dict) -> None:
        self.events.append(event)


def _record() -> CanonicalRecord:
    return CanonicalRecord(
        source_row_number=17,
        source_id="row-17",
        timestamp="2026-04-01T10:00:00Z",
        subject_id="urn:uuid:00000000-0000-4000-8000-000000000017",
        section="CLINICA",
        family="CONSULTA",
        subfamily="OIDO",
        concept="otitis con secreción recurrente",
        composition_section="encounters",
        document_type_code="",
        attributes={
            "Diagnostico": "otitis",
            "Anamnesis": "secreción recurrente; dolor no documentado",
            "ESPECIE": "CANINA",
        },
        species_local="CANINA",
        coding_inputs={ConditionClaim.CODE: "otitis"},
    )


def _context() -> AdapterContext:
    return AdapterContext(
        manufacturer="api-config",
        tenant_id="test-tenant",
        jurisdiction="CA-BC",
        sector="animal-care",
        issuer_did="did:web:issuer.example",
        audience_did="did:web:audience.example",
        language="es-ES",
        data_use="secondary",
        coding_context_fields=("Diagnostico", "Anamnesis", "ESPECIE"),
    )


def test_row_context_is_ranked_without_dropping_ambiguous_candidates() -> None:
    terminology = FakeTerminologyClient()
    ranker = FakeRanker()
    assistant = TerminologyCodingAssistant(context=_context(), terminology=terminology, ranker=ranker)

    suggestions = assistant.suggest_codes(_record())

    assert [item.code for item in suggestions] == ["3135009", "129127001"]
    assert [item.recommendation_percent for item in suggestions] == [56.0, 44.0]
    assert terminology.requests[0].resource_type == "Condition"
    assert terminology.requests[0].field == ConditionClaim.CODE
    assert ranker.requests[0].row_context == {
        "Diagnostico": "otitis",
        "Anamnesis": "secreción recurrente; dolor no documentado",
        "ESPECIE": "CANINA",
    }


def test_pipeline_keeps_unconfirmed_candidates_outside_flat_claims() -> None:
    assistant = TerminologyCodingAssistant(
        context=_context(), terminology=FakeTerminologyClient(), ranker=FakeRanker()
    )

    result = run_pipeline([_record()], _context(), assistant)
    subject = result.composition_message["body"]["data"][0]["resource"]
    condition = next(item for item in subject["contained"] if item["resourceType"] == "Condition")

    claims = condition["meta"]["claims"]
    assert ConditionClaim.CODE not in claims
    assert ConditionClaim.CODE_DISPLAY not in claims
    proposal = condition["meta"]["codingProposals"][0]
    assert [item["code"] for item in proposal["candidates"]] == ["3135009", "129127001"]
    assert proposal["inputText"] == "otitis"
    assert result.summary["codingProposalEntries"] == 1
    assert result.summary["ambiguousCodingProposalEntries"] == 1


def test_human_selection_materializes_code_and_english_display_and_emits_feedback() -> None:
    assistant = TerminologyCodingAssistant(
        context=_context(), terminology=FakeTerminologyClient(), ranker=FakeRanker()
    )
    result = run_pipeline([_record()], _context(), assistant)
    subject = result.composition_message["body"]["data"][0]["resource"]
    condition = next(item for item in subject["contained"] if item["resourceType"] == "Condition")
    proposal = condition["meta"]["codingProposals"][0]
    sink = RecordingFeedbackSink()

    applied = apply_coding_reviews(
        resources=[condition],
        reviews=[{
            "resourceType": "Condition",
            "resourceId": condition["id"],
            "proposalId": proposal["id"],
            "selectedCandidateId": proposal["candidates"][1]["id"],
        }],
        feedback_sink=sink,
        reviewer_subject="did:web:reviewer.example",
    )

    assert applied == 1
    assert condition["meta"]["claims"][ConditionClaim.CODE] == "http://snomed.info/sct|129127001"
    assert condition["meta"]["claims"][ConditionClaim.CODE_DISPLAY] == "Otitis externa"
    assert ConditionClaim.CODE_TEXT not in condition["meta"]["claims"]
    assert sink.events[0]["selectedCandidateId"] == proposal["candidates"][1]["id"]
    assert sink.events[0]["rejectedCandidateIds"] == [proposal["candidates"][0]["id"]]
    assert sink.events[0]["reviewerSubject"] == "did:web:reviewer.example"

    search = InMemorySearchRepository()
    search.upsert(vault_id="reviewed", resource_type="Condition", resource=condition)
    assert search.search(
        vault_id="reviewed",
        resource_type="Condition",
        search_params={"code": "http://snomed.info/sct|129127001"},
    )[0]["id"] == condition["id"]
    assert search.search(
        vault_id="reviewed",
        resource_type="Condition",
        search_params={"code:text": "otitis externa"},
    )[0]["id"] == condition["id"]
