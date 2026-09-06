# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Protocol

from .base import CodingSuggestion
from ..models import AdapterContext, CanonicalRecord


@dataclass(frozen=True)
class TerminologySearchRequest:
    text: str
    language: str
    fhir_version: str
    sector: str
    jurisdiction: str
    resource_type: str
    field: str
    limit: int = 20


@dataclass(frozen=True)
class TerminologyCandidate:
    system: str
    code: str
    display: str
    source: str
    resource_type: str = ""
    field: str = ""
    candidate_id: str = ""


@dataclass(frozen=True)
class CodingRankRequest:
    text: str
    language: str
    sector: str
    jurisdiction: str
    subject_kind: str
    resource_type: str
    field: str
    row_context: dict[str, str]
    candidates: tuple[TerminologyCandidate, ...]


class TerminologyClient(Protocol):
    def search(self, request: TerminologySearchRequest) -> list[TerminologyCandidate]: ...


class CodingRanker(Protocol):
    def rank(self, request: CodingRankRequest) -> list[CodingSuggestion]: ...


def _candidate_id(candidate: TerminologyCandidate) -> str:
    identity = "|".join(
        (candidate.resource_type, candidate.field, candidate.system, candidate.code)
    )
    return sha256(identity.encode("utf-8")).hexdigest()[:24]


def _proposal_id(record: CanonicalRecord, resource_type: str, field: str, text: str) -> str:
    identity = "|".join(
        (record.source_id, str(record.source_row_number), resource_type, field, text)
    )
    return sha256(identity.encode("utf-8")).hexdigest()[:24]


class TerminologyCodingAssistant:
    """Resolve governed candidates, then let a model rank only those candidates."""

    def __init__(self, *, context: AdapterContext, terminology: TerminologyClient, ranker: CodingRanker) -> None:
        self._context = context
        self._terminology = terminology
        self._ranker = ranker

    def suggest_codes(self, record: CanonicalRecord) -> list[CodingSuggestion]:
        suggestions: list[CodingSuggestion] = []
        row_context = self._row_context(record)
        for field, text in record.coding_inputs.items():
            resource_type = str(field or "").split(".", 1)[0].strip()
            input_text = str(text or "").strip()
            if not resource_type or not input_text:
                continue
            request = TerminologySearchRequest(
                text=input_text,
                language=self._context.language,
                fhir_version="R4",
                sector=self._context.sector,
                jurisdiction=self._context.jurisdiction,
                resource_type=resource_type,
                field=str(field),
            )
            candidates = []
            for candidate in self._terminology.search(request):
                enriched = replace(candidate, resource_type=resource_type, field=str(field))
                candidates.append(replace(enriched, candidate_id=_candidate_id(enriched)))
            if not candidates:
                continue
            rank_request = CodingRankRequest(
                text=input_text,
                language=self._context.language,
                sector=self._context.sector,
                jurisdiction=self._context.jurisdiction,
                subject_kind=self._context.subject_kind,
                resource_type=resource_type,
                field=str(field),
                row_context=row_context,
                candidates=tuple(candidates),
            )
            proposal_id = _proposal_id(record, resource_type, str(field), input_text)
            ranked = self._ranker.rank(rank_request)
            by_id = {candidate.candidate_id: candidate for candidate in candidates}
            seen: set[str] = set()
            for item in ranked:
                candidate_id = item.candidate_id or _candidate_id(
                    TerminologyCandidate(
                        system=item.system,
                        code=item.code,
                        display=item.display,
                        source=item.source,
                        resource_type=resource_type,
                        field=str(field),
                    )
                )
                if candidate_id not in by_id or candidate_id in seen:
                    continue
                seen.add(candidate_id)
                suggestions.append(
                    replace(
                        item,
                        resource_type=resource_type,
                        field=str(field),
                        candidate_id=candidate_id,
                        proposal_id=proposal_id,
                    )
                )
            for candidate in candidates:
                if candidate.candidate_id in seen:
                    continue
                suggestions.append(
                    CodingSuggestion.from_candidate(
                        candidate,
                        recommendation_percent=0.0,
                        evidence="not ranked by model",
                        proposal_id=proposal_id,
                    )
                )
        return suggestions

    def _row_context(self, record: CanonicalRecord) -> dict[str, str]:
        allowed = {value.strip() for value in self._context.coding_context_fields if value.strip()}
        if not allowed:
            return {
                "section": record.section,
                "family": record.family,
                "subfamily": record.subfamily,
                "concept": record.concept,
                "species": record.species_local,
            }
        return {
            key: str(value or "").strip()
            for key, value in record.attributes.items()
            if key in allowed and str(value or "").strip()
        }
