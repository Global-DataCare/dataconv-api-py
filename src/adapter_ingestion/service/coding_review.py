# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import csv
import re
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


CODING_PROPOSAL_COLUMN_PREFIX = "coding-proposal:"


def coding_proposal_column(field: str) -> str:
    """Return the non-authoritative optional tabular proposal column name."""

    return f"{CODING_PROPOSAL_COLUMN_PREFIX}{str(field or '').strip()}"


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
    """Project canonical source claims plus non-authoritative proposals."""

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
        candidates = [
            item for item in proposal.get("candidates", []) if isinstance(item, dict)
        ]
        columns[coding_proposal_column(field)] = _csv_value([
            f"{str(item.get('system', '')).strip()}|{str(item.get('code', '')).strip()}"
            for item in candidates
            if str(item.get("system", "")).strip() and str(item.get("code", "")).strip()
        ])
        columns[coding_proposal_column(f"{resource_type}.code-display")] = _csv_value([
            str(item.get("display", "")).strip()
            for item in candidates
            if str(item.get("display", "")).strip()
        ])
        columns[coding_proposal_column(f"{resource_type}.code-text")] = _csv_value([
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
        if not field.startswith(f"{resource_type}.") or not re.fullmatch(
            r"[A-Z][A-Za-z0-9]+\.(?:code|[a-z][a-z0-9-]*-code)",
            field,
        ):
            raise ValueError("coding proposal field does not match the resource")
        claims = meta.setdefault("claims", {})
        claims[field] = f"{selected['system']}|{selected['code']}"
        claims[f"{field}-display"] = str(selected["display"])
        claims[f"{resource_type}.userSelected"] = "true"
        proposal["status"] = "accepted"
        proposal["selectedCandidateId"] = selected_id
        proposal["userSelected"] = True
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


def has_pending_coding_proposals(resource: dict[str, Any]) -> bool:
    """Return true only for unresolved resource-owned review proposals."""

    meta = resource.get("meta", {})
    proposals = meta.get("codingProposals", []) if isinstance(meta, dict) else []
    return any(
        isinstance(proposal, dict) and str(proposal.get("status", "")).strip() == "proposed"
        for proposal in proposals if isinstance(proposals, list)
    )
