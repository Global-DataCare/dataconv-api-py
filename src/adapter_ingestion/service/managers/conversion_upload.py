# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
import base64
import gzip
from urllib.parse import quote
import uuid

from ...runtime import ConfigKey, JobRequest
from ...models import STANDALONE_REPORT_DATA_USE
from ..api_support import (
    HTTPException,
    _coerce_bool,
    _enforce_auth_context,
    _extract_didcomm_attachment_payload,
    _extract_iss,
    _extract_payload_value,
    _extract_requested_by,
    _extract_required_type,
    _enforce_supported_scope,
    _job_log_fields,
    _merge_multipart_metadata,
    _normalize_country_code,
    _require_epoch_seconds,
    _resolve_manufacturer_and_version,
    _resolve_upload_source_format,
    _validate_public_iss,
)
from ..api_config import (
    deep_merge_dicts,
    extract_embedded_api_config,
    is_reserved_api_config_software_id,
    with_authoritative_sector,
)
from ..defaults import default_tenant_config_payload
from ..defaults import load_software_id_preset
from ..defaults import resolve_software_id_default_template
from ..observability import log_event
from ..research import build_upload_response_path
from ..research_study import STUDY_REPORT_WORKBOOK_MODE
from ..research_study import research_study_reference as optional_research_study_reference
from ..research_study import require_research_study_reference
from ..research_study import sector_requires_research_study
from ..research_study import sector_requires_professional_research_auth
from ..research_study import standalone_report_workbook_mode_allowed
from .dependencies import ApiManagerDependencies


def _explicit_workbook_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    inline = _extract_payload_value(payload, "inlineConfig")
    schema = inline.get("schemaConfig") if isinstance(inline, dict) else None
    runtime = inline.get("runtimeDefaults") if isinstance(inline, dict) else None
    data_use = runtime.get("dataUse", "secondary") if isinstance(runtime, dict) else "secondary"
    fields = schema.get("fieldMap") if isinstance(schema, dict) else None
    header = schema.get("headerRowIndex") if isinstance(schema, dict) else None
    if (data_use not in ("secondary", STANDALONE_REPORT_DATA_USE) or type(header) is not int or not 0 <= header <= 100 or not isinstance(fields, dict)
            or not 1 <= len(fields) <= 256 or any(
                not isinstance(key, str) or not 0 < len(key.strip()) <= 160
                or not isinstance(value, str) or not 0 < len(value.strip()) <= 256
                for key, value in fields.items()
            )):
        raise HTTPException(status_code=400, detail="An explicit workbook header and field mapping is required")
    return {"schemaConfig": {"headerRowIndex": header, "fieldMap": fields},
            "runtimeDefaults": {"dataUse": data_use, "adapterId": "api-config"}}


class ConversionUploadManager:
    def __init__(self, deps: ApiManagerDependencies) -> None:
        self._deps = deps

    @staticmethod
    def _suffix_from_input_ref(input_ref: str, default_suffix: str) -> str:
        text = str(input_ref or "").strip()
        if not text:
            return default_suffix
        if text.startswith("gs://"):
            _, _, rest = text.partition("gs://")
            _, _, path = rest.partition("/")
            name = path.rsplit("/", 1)[-1] if path else ""
            return Path(name).suffix or default_suffix
        if text.startswith("file://"):
            text = text[len("file://") :]
        return Path(text).suffix or default_suffix

    async def handle(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        software_id: str,
        resource_type: str,
        request: Any,
        response: Any,
        file: Any,
        body: dict[str, Any] | None,
    ) -> None:
        payload = body if isinstance(body, dict) else {}
        _enforce_supported_scope(jurisdiction, sector, self._deps.settings)
        try:
            form_data = await request.form()
        except Exception:
            form_data = None
        payload = _merge_multipart_metadata(payload, form_data)
        manufacturer_name, manufacturer_version = _resolve_manufacturer_and_version(
            software_id,
            str(_extract_payload_value(payload, "softwareVersion") or ""),
        )
        if not manufacturer_name:
            raise HTTPException(status_code=400, detail="software-id is required in path")

        requested_source_format = str(_extract_payload_value(payload, "sourceFormat") or "").strip()
        normalized_source_format = "excel"
        default_suffix = ".xlsx"
        if requested_source_format:
            normalized_source_format, default_suffix = _resolve_upload_source_format(requested_source_format)

        facility_id = ""
        mode = str(_extract_payload_value(payload, "mode") or "persistent").strip().lower()
        send_value = _extract_payload_value(payload, "send")
        send = _coerce_bool(send_value, default=False)
        requested_by = _extract_iss(payload)
        if not requested_by:
            raise HTTPException(status_code=400, detail="iss is required in DIDComm payload")
        _validate_public_iss(requested_by)
        didcomm_type = _extract_required_type(payload)
        if not didcomm_type:
            raise HTTPException(status_code=400, detail="type is required in DIDComm payload")
        issued_at = _require_epoch_seconds(payload, "iat")
        expires_at = _require_epoch_seconds(payload, "exp")
        if expires_at < issued_at:
            raise HTTPException(status_code=400, detail="exp must be greater than or equal to iat")
        try:
            research_study_reference = (
                require_research_study_reference(payload)
                if sector_requires_research_study(sector)
                else optional_research_study_reference(payload)
            )
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
            require_token=True,
            required_scopes={"dataconv.upload"},
            expected_organization=tenant_id,
            expected_research_study=research_study_reference,
            require_study_research=sector_requires_professional_research_auth(sector, self._deps.settings),
        )
        thid = str(_extract_payload_value(payload, "thid") or "").strip()
        if not thid:
            raise HTTPException(status_code=400, detail="thid is required in DIDComm payload")
        input_ref = str(_extract_payload_value(payload, "inputRef") or "").strip()
        inline_config = _extract_payload_value(payload, "inlineConfig")
        inline_runtime = inline_config.get("runtimeDefaults") if isinstance(inline_config, dict) else None
        report_mapping = isinstance(inline_runtime, dict) and inline_runtime.get("dataUse") == STANDALONE_REPORT_DATA_USE
        if mode == STUDY_REPORT_WORKBOOK_MODE or report_mapping:
            if (not report_mapping or not standalone_report_workbook_mode_allowed(self._deps.settings, sector, mode)
                    or send or input_ref or file is None or normalized_source_format != "excel"
                    or Path(str(file.filename or "")).suffix.lower() != ".xlsx"):
                raise HTTPException(
                    status_code=403,
                    detail="Standalone study reports require an uploaded Excel workbook and a per-upload mapping",
                )
            inline_config = _explicit_workbook_mapping(payload)
        elif (getattr(self._deps.settings, "network_mode", "") == "demo"
                and not getattr(self._deps.settings, "demo_mode", False)):
            if (mode != "demo-ephemeral" or send or input_ref or file is None or normalized_source_format != "excel"
                    or not sector_requires_research_study(sector)):
                raise HTTPException(status_code=403, detail="Demo study uploads require a local workbook and a per-upload mapping")
            inline_config = _explicit_workbook_mapping(payload)
        attachment_payload = None if file is not None else _extract_didcomm_attachment_payload(
            payload,
            default_suffix=default_suffix,
        )

        raw_bytes: bytes = b""
        if not input_ref:
            if file is not None:
                raw_bytes = await file.read()
                file_name = str(file.filename or f"input{default_suffix}")
                content_type = str(file.content_type or "application/octet-stream")
            elif attachment_payload is not None:
                raw_bytes, file_name, content_type = attachment_payload
            elif str(_extract_payload_value(payload, "dataBase64") or "").strip():
                try:
                    raw_bytes = base64.b64decode(str(_extract_payload_value(payload, "dataBase64") or "").strip(), validate=True)
                except Exception as exc:
                    raise HTTPException(status_code=400, detail=f"invalid dataBase64: {exc}") from exc
                file_name = f"input{default_suffix}"
                content_type = "application/octet-stream"
            else:
                raw_bytes = await request.body()
                file_name = f"input{default_suffix}"
                content_type = str(request.headers.get("content-type", "application/octet-stream"))

            if not raw_bytes:
                raise HTTPException(status_code=400, detail="empty upload payload and no inputRef provided")

            encoding = str(request.headers.get("content-encoding", "")).strip().lower()
            if encoding == "gzip":
                try:
                    raw_bytes = gzip.decompress(raw_bytes)
                except Exception as exc:
                    raise HTTPException(status_code=400, detail=f"invalid gzip payload: {exc}") from exc

            maximum_workbook_bytes = max(
                1,
                int(getattr(self._deps.settings, "max_research_workbook_bytes", 8 * 1024 * 1024)),
            )
            if (sector_requires_research_study(sector)
                    and normalized_source_format == "excel"
                    and len(raw_bytes) > maximum_workbook_bytes):
                raise HTTPException(
                    status_code=413,
                    detail=f"Excel workbook exceeds the {maximum_workbook_bytes // (1024 * 1024)} MiB upload limit",
                )

            if not requested_source_format:
                lower_name = str(file_name or '').lower()
                normalized_source_format, default_suffix = _resolve_upload_source_format('csv' if lower_name.endswith('.csv') else 'excel')

            object_name = f"uploads/{uuid.uuid4()}-{file_name.replace('/', '_')}"
            input_ref = self._deps.blob_store.put_bytes(
                path=object_name,
                payload=raw_bytes,
                content_type=content_type,
            )

        country_code = _normalize_country_code(jurisdiction)
        normalized_mode = mode or "persistent"
        should_send = send
        effective_thid = thid
        effective_requested_by = _extract_requested_by(payload, requested_by)

        if normalized_mode == "persistent":
            selector = ConfigKey(
                alternate_name=tenant_id,
                manufacturer=manufacturer_name,
                sector=sector,
                manufacturer_version=manufacturer_version,
                country=country_code,
                facility_id=facility_id,
            )
            resolved_config = self._deps.control_plane.resolve_config(selector)
            if is_reserved_api_config_software_id(software_id):
                input_bytes = self._deps.blob_store.get_bytes(input_ref)
                input_suffix = self._suffix_from_input_ref(input_ref, default_suffix)
                with TemporaryDirectory() as workspace:
                    input_path = Path(workspace) / f"input{input_suffix}"
                    input_path.write_bytes(input_bytes)
                    extracted_config = extract_embedded_api_config(input_path)

                if extracted_config:
                    runtime_defaults = extracted_config.get("runtimeDefaults")
                    embedded_software_id = ""
                    if isinstance(runtime_defaults, dict):
                        embedded_software_id = str(runtime_defaults.get("softwareId") or "").strip()
                    if not embedded_software_id:
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                "softwareId api-config requires embedded marker software-id=<value> "
                                "to resolve the implicit target configuration"
                            ),
                        )
                    resolved_embedded_software_id = resolve_software_id_default_template(embedded_software_id)
                    target_manufacturer_name, target_manufacturer_version = _resolve_manufacturer_and_version(
                        resolved_embedded_software_id,
                        "",
                    )
                    target_selector = ConfigKey(
                        alternate_name=tenant_id,
                        manufacturer=target_manufacturer_name,
                        sector=sector,
                        manufacturer_version=target_manufacturer_version,
                        country=country_code,
                        facility_id=facility_id,
                    )
                    target_resolved_config = self._deps.control_plane.resolve_config(target_selector)
                    if target_resolved_config:
                        base_config = dict(target_resolved_config.content or {})
                    else:
                        base_payload = default_tenant_config_payload(self._deps.settings)
                        preset_payload = load_software_id_preset(resolved_embedded_software_id)
                        base_config = (
                            deep_merge_dicts(base_payload, preset_payload)
                            if isinstance(preset_payload, dict)
                            else base_payload
                        )
                    merged_config = with_authoritative_sector(
                        deep_merge_dicts(base_config, extracted_config),
                        sector,
                    )
                    self._deps.control_plane.upsert_config(
                        key=target_selector,
                        content=merged_config,
                        updated_by=effective_requested_by or "system-bootstrap",
                    )
                    # Keep the reserved selector in sync so this same upload can be processed
                    # immediately without requiring a second request under the target software-id.
                    if target_selector != selector:
                        self._deps.control_plane.upsert_config(
                            key=selector,
                            content=merged_config,
                            updated_by=effective_requested_by or "system-bootstrap",
                        )
                elif not resolved_config:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "softwareId api-config requires embedded API-CONFIG rows "
                            "when no reserved configuration exists yet"
                        ),
                    )
            elif not resolved_config:
                base_payload = default_tenant_config_payload(self._deps.settings)
                preset_payload = load_software_id_preset(software_id)
                autoconfig_payload = (
                    deep_merge_dicts(base_payload, preset_payload)
                    if isinstance(preset_payload, dict)
                    else base_payload
                )
                self._deps.control_plane.upsert_config(
                    key=selector,
                    content=autoconfig_payload,
                    updated_by=effective_requested_by or "system-bootstrap",
                )

        job = self._deps.control_plane.submit_job(
            JobRequest(
                alternate_name=tenant_id,
                manufacturer=manufacturer_name,
                sector=sector,
                manufacturer_version=manufacturer_version,
                country=country_code,
                facility_id=facility_id,
                input_ref=input_ref,
                send=should_send,
                requested_by=effective_requested_by,
                mode=normalized_mode,
                inline_config=inline_config if isinstance(inline_config, dict) else {},
                thid=effective_thid,
                research_study_reference=research_study_reference,
            )
        )
        log_event(
            "job_created",
            source="upload",
            mode=normalized_mode,
            send=bool(should_send),
            inputRef=input_ref,
            sourceFormat=normalized_source_format,
            resourceType=str(resource_type or '').strip(),
            **_job_log_fields(job),
        )
        response.headers["Location"] = (
            build_upload_response_path(
                jurisdiction=jurisdiction,
                sector=sector,
                tenant_id=tenant_id,
                software_id=software_id,
                resource_type=resource_type,
                thid=quote(effective_thid, safe=""),
            )
        )
        response.headers["Retry-After"] = "5"
