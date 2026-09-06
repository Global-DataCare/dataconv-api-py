# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse


RESEARCH_SUBJECT_STUDY_CLAIM = "ResearchSubject.study"
RESEARCH_STUDY_SCOPED_SECTORS = frozenset({"onehealth-research", "animal-research"})
_FHIR_ID = re.compile(r"^[A-Za-z0-9\-.]{1,64}$")


def sector_requires_research_study(sector: Any) -> bool:
    """Return whether new conversions in the sector require study correlation."""
    return str(sector or "").strip().lower() in RESEARCH_STUDY_SCOPED_SECTORS


def normalize_research_study_reference(reference: Any) -> str:
    """Return one literal FHIR Reference to ResearchStudy, relative or absolute."""
    value = str(reference or "").strip()
    relative = value.split("/", 1) if "/" in value else []
    if len(relative) == 2 and relative[0] == "ResearchStudy" and _FHIR_ID.fullmatch(relative[1]):
        return value

    parsed = urlparse(value)
    path_parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme in {"http", "https"}
        and parsed.netloc
        and len(path_parts) >= 2
        and path_parts[-2] == "ResearchStudy"
        and _FHIR_ID.fullmatch(path_parts[-1])
        and not parsed.query
        and not parsed.fragment
    ):
        return value
    raise ValueError("researchStudy.reference must be a literal FHIR ResearchStudy reference")


def research_study_reference(payload: dict[str, Any]) -> str:
    """Read the optional `researchStudy` FHIR Reference from a DIDComm envelope/body."""
    raw = payload.get("researchStudy")
    if raw is None and isinstance(payload.get("body"), dict):
        raw = payload["body"].get("researchStudy")
    if raw is None:
        return ""
    if isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("researchStudy must be a FHIR Reference object") from exc
    if not isinstance(raw, dict):
        raise ValueError("researchStudy must be a FHIR Reference object")
    return normalize_research_study_reference(raw.get("reference"))


def require_research_study_reference(payload: dict[str, Any]) -> str:
    """Require the stable study context for a newly submitted research conversion."""
    if not isinstance(payload, dict):
        raise ValueError("researchStudy.reference is required")
    raw = payload.get("researchStudy")
    if raw is None and isinstance(payload.get("body"), dict):
        raw = payload["body"].get("researchStudy")
    if raw is None:
        raise ValueError("researchStudy.reference is required")
    return research_study_reference(payload)
