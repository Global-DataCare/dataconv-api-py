# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from ..api_support import (
    HTTPException,
    _enforce_auth_context,
    _extract_iss,
    _extract_payload_value,
    _extract_query_value,
    _extract_required_type,
    _normalize_country_code,
    _require_epoch_seconds,
    _validate_public_iss,
)
from .dependencies import ApiManagerDependencies


class TenantConfigPollManager:
    def __init__(self, deps: ApiManagerDependencies) -> None:
        self._deps = deps

    def handle(
        self,
        *,
        sector: str,
        tenant_id: str,
        jurisdiction: str,
        software_id: str,
        request: Any,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        payload = body if isinstance(body, dict) else {}
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

        payload_thid = str(_extract_payload_value(payload, "thid") or "").strip()
        query_thid = _extract_query_value(request, "thid")
        if payload_thid and query_thid and payload_thid != query_thid:
            raise HTTPException(status_code=400, detail="thid mismatch between DIDComm payload and query parameter")
        thid = payload_thid or query_thid
        if not thid:
            raise HTTPException(status_code=400, detail="thid is required in DIDComm payload")
        cached = self._deps.config_create_responses.get(thid)
        if not isinstance(cached, dict):
            raise HTTPException(status_code=404, detail="configuration request not found")

        requested_alt = str(tenant_id).strip().lower()
        if str(cached.get("tenantId", "")).strip().lower() != requested_alt:
            raise HTTPException(status_code=404, detail="configuration request not found")
        if str(cached.get("sector", "")).strip().lower() != str(sector).strip().lower():
            raise HTTPException(status_code=404, detail="configuration request not found")
        if str(cached.get("softwareId", "")).strip().lower() != str(software_id).strip().lower():
            raise HTTPException(status_code=404, detail="configuration request not found")
        requested_country = _normalize_country_code(jurisdiction)
        cached_country = str(cached.get("jurisdiction", "")).strip().upper()
        if requested_country and cached_country and requested_country != cached_country:
            raise HTTPException(status_code=404, detail="configuration request not found")

        # TODO(contract-unification): `_create-response` currently uses POP semantics
        # (single-delivery, removed on first successful poll).
        # Decide whether to keep POP here or align with conversion polling retention
        # (non-POP + TTL cleanup) to make async behavior uniform across endpoints.
        consumed = self._deps.config_create_responses.pop(thid, None)
        if not isinstance(consumed, dict):
            raise HTTPException(status_code=404, detail="configuration request not found")
        response_payload = consumed.get("payload")
        if not isinstance(response_payload, dict):
            raise HTTPException(status_code=404, detail="configuration request not found")
        return response_payload
