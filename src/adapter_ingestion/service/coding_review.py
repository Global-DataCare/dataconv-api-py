# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
from typing import Any, Protocol


class CodingFeedbackSink(Protocol):
    def submit(self, event: dict[str, Any]) -> None: ...


class NoopCodingFeedbackSink:
    def submit(self, event: dict[str, Any]) -> None:
        return None


class CompositeCodingFeedbackSink:
    """Requires every configured durable review sink to accept the same event."""

    def __init__(self, *sinks: CodingFeedbackSink) -> None:
        self._sinks = sinks

    def submit(self, event: dict[str, Any]) -> None:
        for sink in self._sinks:
            sink.submit(event)


def _candidate(proposal: dict[str, Any], candidate_id: str) -> dict[str, Any] | None:
    values = proposal.get("candidates", [])
    if not isinstance(values, list):
        return None
    return next(
        (
            item
            for item in values
            if isinstance(item, dict) and str(item.get("id", "")) == candidate_id
        ),
        None,
    )


def _csv_value(values: list[str]) -> str:
    if not values:
        return ""
    output = StringIO()
    csv.writer(output, lineterminator="").writerow(values)
    return output.getvalue()


def coding_review_export_columns(resource: dict[str, Any]) -> dict[str, str]:
    """Project one review resource to collision-free optional tabular columns."""

    resource_type = str(resource.get("resourceType", "")).strip()
    meta = resource.get("meta", {})
    if not resource_type or not isinstance(meta, dict):
        return {}
    claims = meta.get("claims", {})
    columns = {
        str(key): str(value)
        for key, value in claims.items()
        if str(key) != "@context" and str(value or "").strip()
    } if isinstance(claims, dict) else {}
    proposals = meta.get("codingProposals", [])
    if not isinstance(proposals, list):
        return columns
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        field = str(proposal.get("field", "")).strip()
        if not field.startswith(f"{resource_type}."):
            continue
        source_text = str(proposal.get("inputText", "")).strip()
        columns[f"coding-input:{field}"] = source_text
        candidates = [
            item for item in proposal.get("candidates", []) if isinstance(item, dict)
        ]
        columns[f"coding-proposal:{field}"] = _csv_value([
            f"{str(item.get('system', '')).strip()}|{str(item.get('code', '')).strip()}"
            for item in candidates
            if str(item.get("system", "")).strip() and str(item.get("code", "")).strip()
        ])
        columns[f"coding-proposal:{resource_type}.code-display"] = _csv_value([
            str(item.get("display", "")).strip()
            for item in candidates
            if str(item.get("display", "")).strip()
        ])
        columns[f"coding-proposal:{resource_type}.code-text"] = _csv_value([
            str(item.get("text", "")).strip()
            for item in candidates
            if str(item.get("text", "")).strip()
        ])
    return columns


def apply_coding_reviews(
    *,
    resources: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    feedback_sink: CodingFeedbackSink,
    reviewer_subject: str,
) -> int:
    """Apply explicit human choices and report accepted/rejected candidates."""

    by_identity = {
        (str(resource.get("resourceType", "")), str(resource.get("id", ""))): resource
        for resource in resources
        if isinstance(resource, dict)
    }
    applied = 0
    for review in reviews:
        resource = by_identity.get(
            (str(review.get("resourceType", "")), str(review.get("resourceId", "")))
        )
        if resource is None:
            raise ValueError("coding review resource was not found")
        meta = resource.get("meta")
        if not isinstance(meta, dict):
            raise ValueError("coding review resource meta is missing")
        proposals = meta.get("codingProposals", [])
        proposal = next(
            (
                item
                for item in proposals
                if isinstance(item, dict) and str(item.get("id", "")) == str(review.get("proposalId", ""))
            ),
            None,
        )
        if proposal is None:
            raise ValueError("coding review proposal was not found")
        selected_id = str(review.get("selectedCandidateId", "")).strip()
        selected = _candidate(proposal, selected_id)
        if selected is None:
            raise ValueError("selected candidate is not part of the proposal")
        field = str(proposal.get("field", "")).strip()
        resource_type = str(resource.get("resourceType", "")).strip()
        if field != f"{resource_type}.code":
            raise ValueError("coding proposal field does not match the resource")
        claims = meta.setdefault("claims", {})
        claims[field] = f"{selected['system']}|{selected['code']}"
        claims[f"{resource_type}.code-display"] = str(selected["display"])
        proposal["status"] = "accepted"
        proposal["selectedCandidateId"] = selected_id
        proposal["reviewedAt"] = datetime.now(timezone.utc).isoformat()
        rejected = [
            str(item.get("id", ""))
            for item in proposal.get("candidates", [])
            if isinstance(item, dict) and str(item.get("id", "")) != selected_id
        ]
        feedback_sink.submit(
            {
                "type": "coding-review-feedback",
                "proposalId": str(proposal.get("id", "")),
                "resourceType": resource_type,
                "field": field,
                "inputText": str(proposal.get("inputText", "")),
                "language": str(proposal.get("language", "")),
                "fhirVersion": str(proposal.get("fhirVersion", "")),
                "sector": str(proposal.get("sector", "")),
                "jurisdiction": str(proposal.get("jurisdiction", "")),
                "subjectKind": str(proposal.get("subjectKind", "")),
                "rowContext": dict(proposal.get("rowContext", {})),
                "candidates": list(proposal.get("candidates", [])),
                "selectedCandidateId": selected_id,
                "rejectedCandidateIds": rejected,
                "reason": str(review.get("reason", "")).strip(),
                "reviewerSubject": str(reviewer_subject or "").strip(),
            }
        )
        applied += 1
    return applied
