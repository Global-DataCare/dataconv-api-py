# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

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
from ..observability import log_event
from .dependencies import ApiManagerDependencies


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
        auth_header = ""
        try:
            auth_header = str(request.headers.get("authorization", "") or "")
        except Exception:
            auth_header = ""
        _enforce_auth_context(payload, self._deps.settings, authorization_header=auth_header)
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

        if job.status in {"succeeded", "failed"}:
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

        return _job_poll_response(
            job,
            response,
            blob_store=self._deps.blob_store,
            queue_position=queue_position,
            service_iss=self._deps.settings.default_issuer_did,
            audience_did=str(job.request.requested_by or "").strip(),
        )
