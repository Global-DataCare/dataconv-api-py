# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any
from urllib.parse import quote

from ...runtime import ConfigKey
from ..api_support import (
    DIDCOMM_DEFAULT_MESSAGE_TYPE,
    HTTPException,
    _compose_software_id_token,
    _diagnostics_from_error_detail,
    _enforce_auth_context,
    _error_issue_code,
    _extract_config_entry_payload,
    _extract_data_entries,
    _extract_iss,
    _extract_payload_value,
    _extract_requested_by,
    _extract_required_type,
    _enforce_supported_scope,
    _normalize_country_code,
    _op_outcome,
    _require_epoch_seconds,
    _resolve_manufacturer_and_version,
    _extract_software_token_from_entry,
    _validate_public_iss,
)
from ..api_config import is_reserved_api_config_software_id
from ..defaults import default_tenant_config_payload
from ..defaults import load_software_id_preset
from ..research import build_config_create_response_path
from .dependencies import ApiManagerDependencies


class TenantConfigCreateManager:
    def __init__(self, deps: ApiManagerDependencies) -> None:
        self._deps = deps

    @staticmethod
    def _deep_merge_defaults(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for key, value in (base or {}).items():
            if isinstance(value, dict):
                merged[key] = dict(value)
            else:
                merged[key] = value
        for key, value in (override or {}).items():
            existing = merged.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                merged[key] = TenantConfigCreateManager._deep_merge_defaults(existing, value)
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _to_public_config(payload: dict[str, Any]) -> dict[str, Any]:
        public_payload: dict[str, Any] = dict(payload or {})
        schema_cfg = public_payload.get("schemaConfig")
        if isinstance(schema_cfg, dict):
            if not isinstance(public_payload.get("mappingConfig"), dict):
                public_payload["mappingConfig"] = dict(schema_cfg)
            public_payload.pop("schemaConfig", None)
        return public_payload

    def handle(
        self,
        *,
        sector: str,
        tenant_id: str,
        jurisdiction: str,
        software_id: str,
        request: Any,
        response: Any,
        body: dict[str, Any],
    ) -> None:
        payload = body if isinstance(body, dict) else {}
        _enforce_supported_scope(jurisdiction, sector, self._deps.settings)
        thid = str(_extract_payload_value(payload, "thid") or "").strip()
        didcomm_type = str(_extract_payload_value(payload, "type") or "").strip() or DIDCOMM_DEFAULT_MESSAGE_TYPE
        country_code = _normalize_country_code(jurisdiction)
        if not thid:
            raise HTTPException(status_code=400, detail="thid is required in DIDComm payload")

        def _cache_terminal_response(
            *,
            status_code: int,
            diagnostics: str,
            issue_code: str,
            severity: str,
            entries: list[dict[str, Any]] | None = None,
            data_entries: list[dict[str, Any]] | None = None,
        ) -> None:
            final_entries: list[dict[str, Any]] = []
            if data_entries:
                final_entries = list(data_entries)
            else:
                entry_items = entries or []
                operation_outcome = _op_outcome(
                    severity=severity,
                    code=issue_code,
                    diagnostics=diagnostics,
                )
                for item in entry_items:
                    final_entries.append(
                        {
                            "type": "TenantAdapterConfig",
                            "resource": item,
                            "response": {
                                "status": str(status_code),
                                "outcome": operation_outcome,
                            },
                        }
                    )
                if not final_entries:
                    final_entries.append(
                        {
                            "type": "OperationOutcome",
                            "resource": operation_outcome,
                            "response": {
                                "status": str(status_code),
                                "outcome": operation_outcome,
                            },
                        }
                    )
            issued_at = int(datetime.now(timezone.utc).timestamp())
            self._deps.config_create_responses[thid] = {
                "tenantId": str(tenant_id).strip().lower(),
                "sector": str(sector).strip().lower(),
                "softwareId": str(software_id).strip().lower(),
                "jurisdiction": country_code,
                "payload": {
                    "jti": str(uuid.uuid4()),
                    "thid": thid,
                    "iss": str(self._deps.settings.default_issuer_did or "").strip(),
                    "aud": str(base_requested_by or "").strip(),
                    "type": didcomm_type,
                    "iat": issued_at,
                    "exp": issued_at + 300,
                    "body": {
                        "resourceType": "Bundle",
                        "type": "batch-response",
                        "data": final_entries,
                        "total": len(final_entries),
                        "issues": _op_outcome(
                            severity=severity,
                            code=issue_code,
                            diagnostics=diagnostics,
                        ),
                    },
                },
            }

        base_requested_by = ""
        try:
            base_requested_by = _extract_iss(payload)
            if not base_requested_by:
                raise HTTPException(status_code=400, detail="iss is required in DIDComm payload")
            _validate_public_iss(base_requested_by)
            required_type = _extract_required_type(payload)
            if not required_type:
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
            _enforce_auth_context(
                payload,
                self._deps.settings,
                authorization_header=auth_header,
                require_token=True,
                expected_organization=tenant_id,
            )
            if is_reserved_api_config_software_id(software_id):
                raise HTTPException(
                    status_code=400,
                    detail="softwareId api-config is reserved and cannot be created via config/_create",
                )
            entries = _extract_data_entries(payload)
            if not entries:
                entries = [payload] if payload else [{}]

            data_entries: list[dict[str, Any]] = []
            success_count = 0
            failure_count = 0
            for entry in entries:
                requested_by = str(entry.get("updatedBy") or "").strip() or _extract_requested_by(entry, base_requested_by)
                entry_outcome_status = "200"
                try:
                    unsupported_legacy_keys = [
                        key
                        for key in ("manufacturer", "manufacturerVersion", "schemaConfig", "payload", "resource")
                        if key in entry
                    ]
                    if unsupported_legacy_keys:
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                "legacy entry fields are not supported: "
                                + ", ".join(sorted(unsupported_legacy_keys))
                                + ". Use softwareId/softwareVersion and config.mappingConfig."
                            ),
                        )
                    mislocated_config_keys = [
                        key
                        for key in ("mappingConfig", "speciesFhir", "speciesLocalToFhirCode", "runtimeDefaults")
                        if key in entry
                    ]
                    if mislocated_config_keys and "config" not in entry:
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                "configuration fields must be under entry.config: "
                                + ", ".join(sorted(mislocated_config_keys))
                            ),
                        )
                    entry_software_token, entry_software_version = _extract_software_token_from_entry(entry)
                    if entry_software_token and entry_software_token != software_id:
                        raise HTTPException(status_code=400, detail="softwareId in path and payload must match")
                    if not entry_software_token:
                        entry_software_token = software_id
                    if is_reserved_api_config_software_id(entry_software_token):
                        raise HTTPException(
                            status_code=400,
                            detail="softwareId api-config is reserved and cannot be created via config/_create",
                        )
                    entry_manufacturer, entry_version = _resolve_manufacturer_and_version(
                        entry_software_token,
                        entry_software_version,
                    )
                    if not entry_manufacturer:
                        raise HTTPException(
                            status_code=400,
                            detail="softwareId is required in entry.softwareId",
                        )
                    entry_facility = ""
                    entry_payload = _extract_config_entry_payload(entry)
                    default_payload = default_tenant_config_payload(self._deps.settings)
                    preset_payload = load_software_id_preset(entry_software_token)
                    base_payload = (
                        self._deep_merge_defaults(default_payload, preset_payload)
                        if isinstance(preset_payload, dict)
                        else default_payload
                    )
                    if not entry_payload:
                        entry_payload = base_payload
                    else:
                        entry_payload = self._deep_merge_defaults(base_payload, entry_payload)

                    stored = self._deps.control_plane.upsert_config(
                        key=ConfigKey(
                            alternate_name=tenant_id,
                            manufacturer=entry_manufacturer,
                            sector=sector,
                            manufacturer_version=entry_version,
                            country=country_code,
                            facility_id=entry_facility,
                        ),
                        content=entry_payload,
                        updated_by=requested_by,
                    )
                    success_count += 1
                    data_entries.append(
                        {
                            "type": "TenantAdapterConfig",
                            "resource": {
                                "id": str(stored.object_id),
                                "type": str(stored.object_type),
                                "tenantId": stored.key.alternate_name,
                                "sector": stored.key.sector,
                                "softwareId": _compose_software_id_token(
                                    stored.key.manufacturer,
                                    stored.key.manufacturer_version,
                                ),
                                "country": stored.key.country,
                                "facilityId": stored.key.facility_id,
                                "revision": str(stored.revision),
                                "createdAt": str(stored.created_at),
                                "updatedAt": str(stored.updated_at),
                                "audit": dict(stored.audit or {}),
                                "content": self._to_public_config(stored.content),
                            },
                            "response": {
                                "status": entry_outcome_status,
                                "outcome": _op_outcome(
                                    severity="information",
                                    code="informational",
                                    diagnostics="Configuration accepted.",
                                ),
                            },
                        }
                    )
                except HTTPException as entry_exc:
                    failure_count += 1
                    status_code = int(getattr(entry_exc, "status_code", 400) or 400)
                    entry_outcome_status = str(status_code)
                    diagnostics = _diagnostics_from_error_detail(
                        getattr(entry_exc, "detail", "configuration entry failed")
                    )
                    preview_content: dict[str, Any] = {}
                    try:
                        preview_payload = _extract_config_entry_payload(entry)
                        if preview_payload:
                            preview_payload = self._deep_merge_defaults(
                                default_tenant_config_payload(self._deps.settings),
                                preview_payload,
                            )
                            preview_content = self._to_public_config(preview_payload)
                    except Exception:
                        preview_content = {}

                    software_token = str(entry.get("softwareId") or "").strip()
                    software_version = str(entry.get("softwareVersion") or "").strip()
                    manufacturer_preview, version_preview = _resolve_manufacturer_and_version(
                        software_token,
                        software_version,
                    )
                    software_id_preview = (
                        _compose_software_id_token(manufacturer_preview, version_preview)
                        if manufacturer_preview
                        else software_token
                    )
                    now_ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                    data_entries.append(
                        {
                            "type": "TenantAdapterConfig",
                                "resource": {
                                    "id": str(uuid.uuid4()),
                                    "type": "tenant-adapter-config",
                                    "tenantId": str(tenant_id).strip().lower(),
                                    "sector": str(sector).strip().lower(),
                                    "softwareId": software_id_preview,
                                "country": country_code,
                                "facilityId": "",
                                "revision": "0",
                                "createdAt": now_ts,
                                "updatedAt": now_ts,
                                "audit": {
                                    "createdBy": requested_by,
                                    "updatedBy": requested_by,
                                    "txId": "",
                                    "txTime": "",
                                },
                                "content": preview_content,
                            },
                            "response": {
                                "status": entry_outcome_status,
                                "outcome": _op_outcome(
                                    severity="error",
                                    code=_error_issue_code(status_code),
                                    diagnostics=diagnostics,
                                ),
                            },
                        }
                    )
                except Exception:
                    failure_count += 1
                    now_ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                    data_entries.append(
                        {
                            "type": "TenantAdapterConfig",
                                "resource": {
                                    "id": str(uuid.uuid4()),
                                    "type": "tenant-adapter-config",
                                    "tenantId": str(tenant_id).strip().lower(),
                                    "sector": str(sector).strip().lower(),
                                    "softwareId": str(entry.get("softwareId") or software_id).strip(),
                                "country": country_code,
                                "facilityId": "",
                                "revision": "0",
                                "createdAt": now_ts,
                                "updatedAt": now_ts,
                                "audit": {
                                    "createdBy": requested_by,
                                    "updatedBy": requested_by,
                                    "txId": "",
                                    "txTime": "",
                                },
                                "content": {},
                            },
                            "response": {
                                "status": "500",
                                "outcome": _op_outcome(
                                    severity="error",
                                    code=_error_issue_code(500),
                                    diagnostics="internal server error",
                                ),
                            },
                        }
                    )

            diagnostics = (
                f"Configuration accepted for {success_count} entry(ies)."
                if failure_count == 0
                else f"Configuration processed: {success_count} succeeded, {failure_count} failed."
            )
            _cache_terminal_response(
                status_code=200,
                diagnostics=diagnostics,
                issue_code="informational" if failure_count == 0 else "processing",
                severity="information" if failure_count == 0 else "warning",
                data_entries=data_entries,
            )
        except HTTPException as exc:
            status_code = int(getattr(exc, "status_code", 400) or 400)
            diagnostics = _diagnostics_from_error_detail(getattr(exc, "detail", "configuration request failed"))
            _cache_terminal_response(
                status_code=status_code,
                diagnostics=diagnostics,
                issue_code=_error_issue_code(status_code),
                severity="error",
                entries=[],
            )
        except Exception:
            _cache_terminal_response(
                status_code=500,
                diagnostics="internal server error",
                issue_code=_error_issue_code(500),
                severity="error",
                entries=[],
            )

        response.headers["Location"] = build_config_create_response_path(
            jurisdiction=jurisdiction,
            sector=sector,
            tenant_id=tenant_id,
            software_id=software_id,
            thid=quote(thid, safe=""),
        )
        response.headers["Retry-After"] = "1"
        return None
