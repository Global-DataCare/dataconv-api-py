# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any
from uuid import UUID

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
from ..coding_review import NoopCodingFeedbackSink, apply_coding_reviews, has_pending_coding_proposals
from ..observability import log_event
from .dependencies import ApiManagerDependencies
from ..research_study import research_study_reference, sector_requires_professional_research_auth


def _review_report_row(result: dict[str, Any], review: Any) -> dict[str, Any]:
    if not isinstance(review, dict):
        raise HTTPException(status_code=400, detail="Invalid standalone report review")
    report_id = review.get("reportId")
    try:
        if not isinstance(report_id, str) or str(UUID(report_id)) != report_id:
            raise ValueError("noncanonical report UUID")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid standalone report id") from exc
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
    body = result["body"]
    entry = next((item for item in body["data"] if isinstance(item.get("resource"), dict)
                  and item["resource"].get("resourceType") == "Composition"
                  and item["resource"].get("id") == report_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="Report was not found in the workbook")
    resources = entry["resource"].get("contained", [])
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
    result["body"] = {**body, "data": [entry], "total": 1}
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
            required_scopes={"dataconv.read", "dataconv.review"} if review_report else {"dataconv.read"},
            expected_organization=tenant_id,
            expected_research_study=requested_study,
            require_study_research=review_report or sector_requires_professional_research_auth(sector, self._deps.settings),
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
        if review_report:
            runtime = (job.request.inline_config or {}).get("runtimeDefaults")
            if (self._deps.settings.network_mode != "demo" or self._deps.settings.demo_mode
                    or not stored_study or job.request.mode != "demo-ephemeral" or not isinstance(runtime, dict)
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

        if not review_report and job.status in {"succeeded", "failed"}:
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
        return _review_report_row(result, payload["reportReview"]) if review_report else result
