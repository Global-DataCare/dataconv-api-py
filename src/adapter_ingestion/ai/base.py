# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from ..models import CanonicalRecord


@dataclass(frozen=True)
class CodingSuggestion:
    system: str
    code: str
    display: str
    confidence: float
    evidence: str
    resource_type: str = "DocumentReference"
    field: str = "DocumentReference.event-code"
    source: str = ""
    recommendation_percent: float = 0.0
    candidate_id: str = ""
    proposal_id: str = ""

    @classmethod
    def from_candidate(
        cls,
        candidate,
        *,
        recommendation_percent: float,
        evidence: str,
        proposal_id: str = "",
    ) -> "CodingSuggestion":
        candidate_id = str(getattr(candidate, "candidate_id", "") or "")
        if not candidate_id:
            identity = "|".join(
                (
                    str(candidate.resource_type),
                    str(candidate.field),
                    str(candidate.system),
                    str(candidate.code),
                )
            )
            candidate_id = sha256(identity.encode("utf-8")).hexdigest()[:24]
        return cls(
            system=str(candidate.system),
            code=str(candidate.code),
            display=str(candidate.display),
            confidence=max(0.0, min(1.0, float(recommendation_percent) / 100.0)),
            evidence=str(evidence or ""),
            resource_type=str(candidate.resource_type),
            field=str(candidate.field),
            source=str(candidate.source or ""),
            recommendation_percent=max(0.0, min(100.0, float(recommendation_percent))),
            candidate_id=candidate_id,
            proposal_id=str(proposal_id or ""),
        )


class CodingAssistant:
    def suggest_codes(self, record: CanonicalRecord) -> list[CodingSuggestion]:
        raise NotImplementedError


class NoopCodingAssistant:
    def suggest_codes(self, record: CanonicalRecord) -> list[CodingSuggestion]:
        return []
