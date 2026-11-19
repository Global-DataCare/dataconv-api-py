# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any
from uuid import UUID

from ...ai.terminology import TerminologyClient
from ...models import STANDALONE_REPORT_DATA_USE
from ..api_support import (
    HTTPException,
    _enforce_auth_context,
    _extract_iss,
    _extract_query_value,
    _extract_required_type,
    _enforce_supported_scope,
    _job_is_expired,
    _job_log_fields,
    _job_poll_response,
    _normalize_country_code,
    _require_epoch_seconds,
    _resolve_manufacturer_and_version,
    _validate_public_iss,
)
from ..coding_candidates import CodingCandidateQuery, search_coding_candidates
from ..coding_review import NoopCodingFeedbackSink, apply_coding_reviews, has_pending_coding_proposals
from ..observability import log_event
from .dependencies import ApiManagerDependencies
from ..research_study import (
    research_study_reference,
    sector_requires_professional_research_auth,
    standalone_report_workbook_mode_allowed,
)


def _report_row(result: dict[str, Any], operation: Any) -> dict[str, Any]:
    if not isinstance(operation, dict):
        raise HTTPException(status_code=400, detail="Invalid standalone report review")
    report_id = operation.get("reportId")
    try:
        if not isinstance(report_id, str) or str(UUID(report_id)) != report_id:
            raise ValueError("noncanonical report UUID")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid standalone report id") from exc
    entry = next((item for item in result["body"]["data"] if isinstance(item.get("resource"), dict)
                  and item["resource"].get("resourceType") == "Composition"
                  and item["resource"].get("id") == report_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="Report was not found in the workbook")
    return entry


def _report_proposal(resources: list[dict[str, Any]], target: dict[str, Any]) -> dict[str, Any]:
    for resource in resources:
        if resource.get("resourceType") != target.get("resourceType") or resource.get("id") != target.get("resourceId"):
            continue
        for proposal in resource.get("meta", {}).get("codingProposals", []):
            if proposal.get("id") == target.get("proposalId") and proposal.get("status") == "proposed":
                return proposal
    raise HTTPException(status_code=400, detail="Coding proposal was not found in this report row")


def _review_report_row(result: dict[str, Any], review: Any, terminology: TerminologyClient | None, *,
                       sector: str, jurisdiction: str) -> dict[str, Any]:
    entry = _report_row(result, review)
    decisions = review.get("codingReviews")
    keys = ("resourceType", "resourceId", "proposalId", "selectedCandidateId")
    if not isinstance(decisions, list) or len(decisions) > 100 or any(
        not isinstance(item, dict) or any(
            not isinstance(item.get(key), str) or not 0 < len(item[key]) <= 160 for key in keys
        ) for item in decisions
    ):
        raise HTTPException(status_code=400, detail="Invalid standalone report coding decisions")
    if len({tuple(item[key] for key in keys[:3]) for item in decisions}) != len(decisions):
        raise HTTPException(status_code=400, detail="Duplicate standalone report coding decision")
    resources = entry["resource"].get("contained", [])
    for decision in decisions:
        proposal = _report_proposal(resources, decision)
        if any(item.get("id") == decision["selectedCandidateId"] for item in proposal.get("candidates", [])):
            continue
        query = decision.get("terminologyQuery")
        if isinstance(query, dict):
            proposal["candidates"] = search_coding_candidates(terminology, query=CodingCandidateQuery.parse(query),
                sector=sector, jurisdiction=jurisdiction, resource_type=decision["resourceType"], proposal=proposal)
    try:
        # This projects a reviewed row without changing the conversion artifact.
        # The consuming Research workspace commits publication and its audit record.
        apply_coding_reviews(resources=resources, reviews=decisions, feedback_sink=NoopCodingFeedbackSink(),
                             reviewer_subject="")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if any(has_pending_coding_proposals(resource) for resource in resources):
        raise HTTPException(status_code=409, detail="Resolve the report row's coding proposals before publication")
    result.pop("attachments", None)
    result["body"] = {**result["body"], "data": [entry], "total": 1}
    return result


def _search_report_candidates(result: dict[str, Any], search: Any, terminology: TerminologyClient | None, *,
                              sector: str, jurisdiction: str) -> dict[str, Any]:
    entry = _report_row(result, search)
    proposal = _report_proposal(entry["resource"].get("contained", []), search)
    candidates = search_coding_candidates(terminology, query=CodingCandidateQuery.parse(search), sector=sector,
        jurisdiction=jurisdiction, resource_type=search["resourceType"], proposal=proposal)
    result.pop("attachments", None)
    result["body"] = {"reportId": search["reportId"], "proposalId": search["proposalId"], "candidates": candidates}
    return result


class ConversionUploadPollManager:
    def __init__(self, deps: ApiManagerDependencies) -> None:
        self._deps = deps

    def handle(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        software_id: str,
        resource_type: str,
        response: Any,
        request: Any,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        payload = body if isinstance(body, dict) else {}
        review_report = "reportReview" in payload
        search_report = "reportCandidateSearch" in payload
        if review_report and search_report:
            raise HTTPException(status_code=400, detail="Use one report operation per request")
        report_operation = review_report or search_report
        _enforce_supported_scope(jurisdiction, sector, self._deps.settings)
        issuer = _extract_iss(payload)
        if not issuer:
            raise HTTPException(status_code=400, detail="iss is required in DIDComm payload")
        _validate_public_iss(issuer)
        didcomm_type = _extract_required_type(payload)
        if not didcomm_type:
            raise HTTPException(status_code=400, detail="type is required in DIDComm payload")
        issued_at = _require_epoch_seconds(payload, "iat")
        expires_at = _require_epoch_seconds(payload, "exp")
        if expires_at < issued_at:
            raise HTTPException(status_code=400, detail="exp must be greater than or equal to iat")
        try:
            requested_study = research_study_reference(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        auth_header = ""
        try:
            auth_header = str(request.headers.get("authorization", "") or "")
        except Exception:
            auth_header = ""
        _enforce_auth_context(
            payload,
            self._deps.settings,
            authorization_header=auth_header,
            required_scopes={"dataconv.read", "dataconv.review"} if report_operation else {"dataconv.read"},
            expected_organization=tenant_id,
            expected_research_study=requested_study,
            require_study_research=report_operation or sector_requires_professional_research_auth(sector, self._deps.settings),
        )
        payload_thid = str(payload.get("thid", "")).strip()
        query_thid = _extract_query_value(request, "thid")
        if payload_thid and query_thid and payload_thid != query_thid:
            raise HTTPException(status_code=400, detail="thid mismatch between DIDComm payload and query parameter")
        thid = payload_thid or query_thid
        if not thid:
            raise HTTPException(status_code=400, detail="thid is required in DIDComm payload")

        job = self._deps.control_plane.get_job_by_thid(thid)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")

        stored_study = str(job.request.research_study_reference or "").strip()
        if stored_study and not requested_study:
            raise HTTPException(status_code=400, detail="researchStudy.reference is required")
        if requested_study and requested_study != stored_study:
            raise HTTPException(status_code=404, detail="job not found")

        if str(job.request.alternate_name).strip().lower() != str(tenant_id).strip().lower():
            raise HTTPException(status_code=404, detail="job not found")
        if str(job.request.sector).strip().lower() != str(sector).strip().lower():
            raise HTTPException(status_code=404, detail="job not found")
        requested_manufacturer, requested_version = _resolve_manufacturer_and_version(software_id, "")
        if str(job.request.manufacturer).strip().lower() != requested_manufacturer:
            raise HTTPException(status_code=404, detail="job not found")
        if str(job.request.manufacturer_version).strip().lower() != requested_version:
            raise HTTPException(status_code=404, detail="job not found")
        country_code = _normalize_country_code(jurisdiction)
        if country_code and str(job.request.country).strip().upper() != country_code:
            raise HTTPException(status_code=404, detail="job not found")
        if report_operation:
            runtime = (job.request.inline_config or {}).get("runtimeDefaults")
            if (not standalone_report_workbook_mode_allowed(self._deps.settings, sector, job.request.mode)
                    or not stored_study or job.request.send or not isinstance(runtime, dict)
                    or runtime.get("dataUse") != STANDALONE_REPORT_DATA_USE):
                raise HTTPException(status_code=404, detail="Standalone report job not found")
            if job.status != "succeeded":
                raise HTTPException(status_code=409, detail="Standalone report workbook is not ready for review")
        if _job_is_expired(job, self._deps.settings.job_result_ttl_seconds):
            deleted = self._deps.control_plane.delete_job(job.job_id)
            log_event(
                "job_expired_deleted",
                source="upload-response",
                deleted=bool(deleted),
                delivered=bool(str(job.delivered_at or "").strip()),
                **_job_log_fields(job),
            )
            raise HTTPException(status_code=404, detail="job expired")

        if not report_operation and job.status in {"succeeded", "failed"}:
            first_delivery = not bool(str(job.delivered_at or "").strip())
            if first_delivery:
                job = self._deps.control_plane.mark_job_delivered(job.job_id)
            log_event(
                "job_response_delivered",
                source="upload-response",
                firstDelivery=first_delivery,
                **_job_log_fields(job),
            )

        queue_position = None
        if job.status == "queued":
            queue_position = self._deps.control_plane.get_queue_position(job.job_id)

        result = _job_poll_response(
            job,
            response,
            blob_store=self._deps.blob_store,
            queue_position=queue_position,
            service_iss=self._deps.settings.default_issuer_did,
            audience_did=str(job.request.requested_by or "").strip(),
        )
        if review_report:
            return _review_report_row(result, payload["reportReview"], self._deps.terminology_client,
                                      sector=sector, jurisdiction=jurisdiction)
        if search_report:
            return _search_report_candidates(result, payload["reportCandidateSearch"], self._deps.terminology_client,
                                             sector=sector, jurisdiction=jurisdiction)
        return result
