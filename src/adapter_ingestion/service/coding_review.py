# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol


class CodingFeedbackSink(Protocol):
    def submit(self, event: dict[str, Any]) -> None: ...


class NoopCodingFeedbackSink:
    def submit(self, event: dict[str, Any]) -> None:
        return None


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
        claims.pop(f"{resource_type}.code-text", None)
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
