from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Any

from fastapi import HTTPException

from ..ai.terminology import TerminologyCandidate, TerminologyClient, TerminologySearchRequest


@dataclass(frozen=True)
class CodingCandidateQuery:
    text: str
    language: str
    sources: tuple[str, ...]

    @classmethod
    def parse(cls, payload: dict[str, Any]) -> CodingCandidateQuery:
        text = str(payload.get("text", "") or "").strip()
        language = str(payload.get("language", "") or "").strip()
        raw_sources = payload.get("sources", [])
        if not 2 <= len(text) <= 160:
            raise HTTPException(status_code=400, detail="text must contain between 2 and 160 characters")
        if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language):
            raise HTTPException(status_code=400, detail="language must be a valid BCP 47 tag")
        if not isinstance(raw_sources, list) or len(raw_sources) > 10:
            raise HTTPException(status_code=400, detail="sources must be a bounded list")
        sources = tuple(str(value or "").strip() for value in raw_sources)
        if any(not re.fullmatch(r"[A-Z][A-Z0-9_]{1,31}", value) for value in sources):
            raise HTTPException(status_code=400, detail="source is invalid")
        return cls(text=text, language=language, sources=sources)


def coding_candidate(resource_type: str, field: str, value: TerminologyCandidate) -> dict[str, Any]:
    return {
        "id": sha256("|".join((resource_type, field, value.system, value.code)).encode("utf-8")).hexdigest()[:24],
        "system": value.system,
        "code": value.code,
        "display": value.display,
        "source": value.source,
        "recommendationPercent": 0.0,
        "evidence": "terminology candidate",
    }


def search_coding_candidates(
    terminology: TerminologyClient | None, *, query: CodingCandidateQuery, sector: str, jurisdiction: str,
    resource_type: str, proposal: dict[str, Any],
) -> list[dict[str, Any]]:
    if terminology is None:
        raise HTTPException(status_code=503, detail="terminology service is not configured")
    field = str(proposal.get("field", "") or "").strip()
    if not re.fullmatch(rf"{re.escape(resource_type)}\.(?:code|[a-z][a-z0-9-]*-code)", field):
        raise HTTPException(status_code=409, detail="proposal field does not match the resource")
    found = terminology.search(TerminologySearchRequest(
        text=query.text, language=query.language, fhir_version="R4", sector=sector, jurisdiction=jurisdiction,
        resource_type=resource_type, field=field, sources=query.sources, limit=50,
    ))
    merged = {
        str(item["id"]): item for item in proposal.get("candidates", [])
        if isinstance(item, dict) and str(item.get("id", ""))
    }
    for value in found:
        candidate = coding_candidate(resource_type, field, value)
        merged[candidate["id"]] = candidate
    return list(merged.values())
