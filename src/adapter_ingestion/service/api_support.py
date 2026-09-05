# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path as FilePath
from typing import Any
import base64
import json
import mimetypes
import os
import ssl
import uuid
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse
from urllib.request import Request as UrlRequest, urlopen

from .auth_exchange import validate_session_access_token

try:
    import certifi
except ImportError:  # pragma: no cover - optional runtime dependency
    certifi = None  # type: ignore[assignment]

try:
    from fastapi import Body, FastAPI, File, HTTPException, Path, Request, Response, UploadFile
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import HTMLResponse
    from fastapi.responses import JSONResponse
except ImportError:  # pragma: no cover - optional runtime dependency
    Body = None  # type: ignore[assignment]
    FastAPI = None  # type: ignore[assignment]
    File = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]
    Path = None  # type: ignore[assignment]
    Request = None  # type: ignore[assignment]
    Response = None  # type: ignore[assignment]
    UploadFile = None  # type: ignore[assignment]
    RequestValidationError = None  # type: ignore[assignment]
    HTMLResponse = None  # type: ignore[assignment]
    JSONResponse = None  # type: ignore[assignment]


DIDCOMM_PLAINTEXT_MEDIA_TYPE = "application/didcomm-plain+json"
DIDCOMM_DEFAULT_MESSAGE_TYPE = "https://didcomm.org/plaintext/2.0/message"


if JSONResponse is not None:

    class DidcommJSONResponse(JSONResponse):
        media_type = DIDCOMM_PLAINTEXT_MEDIA_TYPE

else:  # pragma: no cover - optional runtime dependency
    DidcommJSONResponse = None  # type: ignore[assignment]


def build_api_docs_html(*, openapi_url: str = "/openapi.json") -> str:
    return f"""<!DOCTYPE html>
<html>
  <head>
    <meta charset="UTF-8" />
    <title>Preconversion API Docs</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css" />
    <style>
      html, body, #swagger-ui {{
        margin: 0;
        padding: 0;
        height: 100%;
      }}
    </style>
  </head>
  <body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
      function parseObjectJson(raw) {{
        if (!raw) return null;
        if (typeof raw === 'object') return raw;
        try {{
          return JSON.parse(raw);
        }} catch {{
          return null;
        }}
      }}

      function buildDidcommTimeToken() {{
        const now = new Date();
        const yyyy = String(now.getUTCFullYear());
        const mm = String(now.getUTCMonth() + 1).padStart(2, '0');
        const dd = String(now.getUTCDate()).padStart(2, '0');
        const hh = String(now.getUTCHours()).padStart(2, '0');
        const mi = String(now.getUTCMinutes()).padStart(2, '0');
        return `${{yyyy}}${{mm}}${{dd}}${{hh}}${{mi}}`;
      }}

      function shouldAutoToken(value, prefix) {{
        return String(value || '').trim() === `${{prefix}}-auto`;
      }}

      function normalizeDropboxDirectDownloadUrl(rawUrl) {{
        try {{
          const url = new URL(String(rawUrl || ''));
          if (!url.hostname.toLowerCase().includes('dropbox.com')) return rawUrl;
          url.searchParams.set('dl', '1');
          return url.toString();
        }} catch {{
          return rawUrl;
        }}
      }}

      function normalizeDidcommAttachmentLinks(payload) {{
        if (!payload || typeof payload !== 'object') return;
        if (!Array.isArray(payload.attachments)) return;
        payload.attachments.forEach(function (attachment) {{
          if (!attachment || typeof attachment !== 'object') return;
          const data = attachment.data;
          if (!data || typeof data !== 'object') return;
          if (!Array.isArray(data.links)) return;
          data.links = data.links.map(function (link) {{
            return normalizeDropboxDirectDownloadUrl(link);
          }});
        }});
      }}

      window.ui = SwaggerUIBundle({{
        url: '{openapi_url}',
        dom_id: '#swagger-ui',
        deepLinking: true,
        docExpansion: 'list',
                defaultModelsExpandDepth: -1,
        presets: [SwaggerUIBundle.presets.apis],
        requestInterceptor: function (req) {{
          try {{
            const headers = req && req.headers ? req.headers : {{}};
            const rawContentType = String(headers['Content-Type'] || headers['content-type'] || '').toLowerCase();
            if (!rawContentType.includes('application/didcomm-plain+json')) {{
              return req;
            }}
            const payload = parseObjectJson(req.body);
            if (!payload) {{
              return req;
            }}
            const stamp = buildDidcommTimeToken();
            if (shouldAutoToken(payload.jti, 'req')) {{
              payload.jti = 'req-' + stamp;
            }}
            if (shouldAutoToken(payload.thid, 'thid')) {{
              payload.thid = 'thid-' + stamp;
            }}
            normalizeDidcommAttachmentLinks(payload);
            req.body = JSON.stringify(payload);
          }} catch {{
          }}
          return req;
        }}
      }});
    </script>
  </body>
</html>"""


def _op_outcome(
    *,
    severity: str = "information",
    code: str = "informational",
    diagnostics: str,
) -> dict[str, Any]:
    return {
        "resourceType": "OperationOutcome",
        "issue": [
            {
                "severity": severity,
                "code": code,
                "diagnostics": diagnostics,
            }
        ],
    }


def _bundle_api_error_envelope(
    *,
    diagnostics: str,
    service_iss: str,
    aud: str = "",
    thid: str = "",
    code: str = "invalid",
    severity: str = "error",
) -> dict[str, Any]:
    return {
        "iss": str(service_iss or "").strip(),
        "aud": str(aud or "").strip(),
        "thid": str(thid or "").strip(),
        "type": "application/bundle-api+json",
        "body": {
            "resourceType": "Bundle",
            "data": [],
            "total": 0,
            "issues": _op_outcome(
                severity=severity,
                code=code,
                diagnostics=diagnostics,
            ),
        },
    }


def _normalize_dropbox_direct_download_url(raw_url: str) -> str:
    text = str(raw_url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    host = parsed.netloc.lower()
    if "dropbox.com" not in host:
        return text
    query_items = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "raw"]
    has_dl = False
    normalized_items: list[tuple[str, str]] = []
    for key, value in query_items:
        if key == "dl":
            normalized_items.append(("dl", "1"))
            has_dl = True
        else:
            normalized_items.append((key, value))
    if not has_dl:
        normalized_items.append(("dl", "1"))
    return urlunparse(parsed._replace(query=urlencode(normalized_items, doseq=True)))


def _normalize_attachment_direct_download_url(raw_url: str) -> str:
    return _normalize_dropbox_direct_download_url(raw_url)


def _attachment_ssl_context() -> ssl.SSLContext:
    # Respect explicit env overrides first. This is needed for corporate proxies or
    # custom internal roots mounted via SSL_CERT_FILE / SSL_CERT_DIR.
    if str(os.environ.get("SSL_CERT_FILE", "") or "").strip() or str(os.environ.get("SSL_CERT_DIR", "") or "").strip():
        return ssl.create_default_context()
    if certifi is not None:
        try:
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
    return ssl.create_default_context()


def _attachment_filename(
    *,
    attachment_id: str,
    filename: str,
    source_url: str,
    default_suffix: str,
) -> str:
    explicit_name = str(filename or "").strip()
    if explicit_name:
        candidate = explicit_name
    else:
        parsed = urlparse(str(source_url or "").strip())
        from_url = unquote(FilePath(parsed.path).name).strip()
        candidate = from_url or str(attachment_id or "").strip() or f"input{default_suffix}"
    if not FilePath(candidate).suffix:
        return f"{candidate}{default_suffix}"
    return candidate


def _attachment_content_type(
    *,
    attachment_media_type: str,
    response_content_type: str,
    file_name: str,
) -> str:
    explicit = str(attachment_media_type or "").strip()
    if explicit:
        return explicit
    response_type = str(response_content_type or "").split(";", 1)[0].strip()
    if response_type:
        return response_type
    guessed, _ = mimetypes.guess_type(file_name)
    return guessed or "application/octet-stream"


def _extract_didcomm_attachment_payload(
    payload: dict[str, Any],
    *,
    default_suffix: str,
    timeout_seconds: int = 30,
) -> tuple[bytes, str, str] | None:
    attachments = payload.get("attachments")
    if not isinstance(attachments, list):
        return None
    if len(attachments) > 1:
        raise HTTPException(
            status_code=400,
            detail="multiple DIDComm attachments are not supported yet; send one attachment per upload request",
        )

    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        data = attachment.get("data")
        if not isinstance(data, dict):
            continue

        attachment_id = str(attachment.get("id", "") or "").strip()
        attachment_filename = str(attachment.get("filename", "") or "").strip()
        attachment_media_type = str(attachment.get("media_type", "") or "").strip()

        raw_base64 = str(data.get("base64", "") or "").strip()
        if raw_base64:
            try:
                raw_bytes = base64.b64decode(raw_base64, validate=True)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"invalid attachment.data.base64: {exc}") from exc
            file_name = _attachment_filename(
                attachment_id=attachment_id,
                filename=attachment_filename,
                source_url="",
                default_suffix=default_suffix,
            )
            content_type = _attachment_content_type(
                attachment_media_type=attachment_media_type,
                response_content_type="",
                file_name=file_name,
            )
            return (raw_bytes, file_name, content_type)

        raw_links = data.get("links")
        if isinstance(raw_links, list):
            normalized_links = [str(item or "").strip() for item in raw_links if str(item or "").strip()]
            if not normalized_links:
                continue
            if len(normalized_links) > 1:
                raise HTTPException(
                    status_code=400,
                    detail="attachment.data.links must contain exactly one URL; do not send multiple links in one attachment",
                )
            first_link = normalized_links[0]
            download_url = _normalize_attachment_direct_download_url(first_link)
            try:
                with urlopen(
                    UrlRequest(download_url, method="GET", headers={"User-Agent": "adapter-ingestion-py/0.1"}),
                    timeout=timeout_seconds,
                    context=_attachment_ssl_context(),
                ) as remote_response:
                    raw_bytes = remote_response.read()
                    response_content_type = str(remote_response.headers.get("Content-Type", "") or "")
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"unable to download attachment link: {exc}") from exc
            if not raw_bytes:
                raise HTTPException(status_code=400, detail="attachment link resolved to an empty payload")
            file_name = _attachment_filename(
                attachment_id=attachment_id,
                filename=attachment_filename,
                source_url=download_url,
                default_suffix=default_suffix,
            )
            content_type = _attachment_content_type(
                attachment_media_type=attachment_media_type,
                response_content_type=response_content_type,
                file_name=file_name,
            )
            return (raw_bytes, file_name, content_type)

    return None


def _diagnostics_from_error_detail(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        diagnostics = detail.get("diagnostics")
        if isinstance(diagnostics, str) and diagnostics.strip():
            return diagnostics.strip()
        try:
            return json.dumps(detail, ensure_ascii=True, sort_keys=True)
        except Exception:
            return str(detail)
    if isinstance(detail, list):
        if detail:
            first = detail[0]
            if isinstance(first, dict):
                msg = first.get("msg")
                loc = first.get("loc")
                if isinstance(msg, str) and msg.strip():
                    if isinstance(loc, (list, tuple)) and loc:
                        return f"{'.'.join(str(p) for p in loc)}: {msg.strip()}"
                    return msg.strip()
        try:
            return json.dumps(detail, ensure_ascii=True, sort_keys=True)
        except Exception:
            return str(detail)
    return str(detail or "request validation failed")


def _error_issue_code(status_code: int) -> str:
    if status_code == 401:
        return "security"
    if status_code == 403:
        return "forbidden"
    if status_code == 404:
        return "not-found"
    if status_code == 409:
        return "conflict"
    return "invalid"


def _parse_iso_utc(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _job_is_expired(job: Any, ttl_seconds: int) -> bool:
    # Negative TTL disables expiration checks.
    if ttl_seconds < 0:
        return False

    status = str(getattr(job, "status", "") or "").strip().lower()
    if status not in {"succeeded", "failed"}:
        return False

    base_ts = str(getattr(job, "finished_at", "") or getattr(job, "created_at", "")).strip()
    base_dt = _parse_iso_utc(base_ts)
    if base_dt is None:
        return False

    now_dt = datetime.now(timezone.utc)
    expiration_dt = base_dt + timedelta(seconds=max(0, int(ttl_seconds)))
    return now_dt >= expiration_dt


def _job_log_fields(job: Any) -> dict[str, Any]:
    request = getattr(job, "request", None)
    manufacturer = str(getattr(request, "manufacturer", "") or "").strip()
    manufacturer_version = str(getattr(request, "manufacturer_version", "") or "").strip()
    software_id = _compose_software_id_token(manufacturer, manufacturer_version)
    return {
        "jobId": str(getattr(job, "job_id", "") or "").strip(),
        "thid": str(getattr(job, "thid", "") or "").strip(),
        "tenantId": str(getattr(request, "alternate_name", "") or "").strip(),
        "manufacturer": manufacturer,
        "manufacturerVersion": manufacturer_version,
        "softwareId": software_id,
        "country": str(getattr(request, "country", "") or "").strip(),
        "status": str(getattr(job, "status", "") or "").strip(),
        "requestedBy": str(getattr(request, "requested_by", "") or "").strip(),
        "createdAt": str(getattr(job, "created_at", "") or "").strip(),
        "finishedAt": str(getattr(job, "finished_at", "") or "").strip(),
        "deliveredAt": str(getattr(job, "delivered_at", "") or "").strip(),
    }


def _extract_data_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("body"), dict):
        data = payload.get("body", {}).get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _extract_config_entry_payload(entry: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}

    config_wrapped = entry.get("config")
    if config_wrapped is None:
        return {}
    if not isinstance(config_wrapped, dict):
        raise HTTPException(status_code=400, detail="entry.config must be an object when provided")

    payload = dict(config_wrapped)
    if "schemaConfig" in payload:
        raise HTTPException(
            status_code=400,
            detail="legacy field config.schemaConfig is not supported; use config.mappingConfig",
        )
    if "manufacturer" in payload or "manufacturerVersion" in payload:
        raise HTTPException(
            status_code=400,
            detail="legacy fields in entry.config are not supported; use softwareId/softwareVersion at entry level",
        )

    mapping = payload.get("mappingConfig")
    if mapping is not None and not isinstance(mapping, dict):
        raise HTTPException(status_code=400, detail="entry.config.mappingConfig must be an object")
    if isinstance(mapping, dict):
        payload["schemaConfig"] = dict(mapping)
    return payload


def _normalize_country_code(jurisdiction: str) -> str:
    value = str(jurisdiction or "").strip()
    if not value:
        return ""
    return value.upper()


def _enforce_supported_scope(jurisdiction: str, sector: str, settings: Any) -> None:
    requested_jurisdiction = _normalize_country_code(jurisdiction)
    requested_sector = str(sector or "").strip().lower()

    supported_jurisdictions = tuple(str(item or "").strip().upper() for item in getattr(settings, "supported_jurisdictions", ("*",)))
    supported_sectors = tuple(str(item or "").strip().lower() for item in getattr(settings, "supported_sectors", ("*",)))

    if supported_jurisdictions and "*" not in supported_jurisdictions:
        if requested_jurisdiction not in supported_jurisdictions:
            raise HTTPException(status_code=404, detail=f"jurisdiction not supported: {requested_jurisdiction}")

    if supported_sectors and "*" not in supported_sectors:
        if requested_sector not in supported_sectors:
            raise HTTPException(status_code=404, detail=f"sector not supported: {requested_sector}")


def _resolve_upload_source_format(source_format: str) -> tuple[str, str]:
    normalized = str(source_format or "").strip().lower()
    if normalized in {"excel", "xlsx"}:
        return ("excel", ".xlsx")
    if normalized == "csv":
        return ("csv", ".csv")
    raise HTTPException(status_code=400, detail="source_format must be 'csv' or 'excel'")


def _extract_requested_by(payload: dict[str, Any], explicit_requested_by: str = "") -> str:
    explicit = str(explicit_requested_by or "").strip()
    if explicit:
        return explicit

    for candidate_key in ("requestedBy", "iss", "from"):
        value = payload.get(candidate_key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    nested_body = payload.get("body")
    if isinstance(nested_body, dict):
        for candidate_key in ("requestedBy", "iss", "from"):
            value = nested_body.get(candidate_key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return ""


def _extract_payload_value(payload: dict[str, Any], key: str) -> Any:
    value = payload.get(key)
    if value not in (None, ""):
        return value
    nested_body = payload.get("body")
    if isinstance(nested_body, dict):
        return nested_body.get(key)
    return None


def _extract_query_value(request: Any, key: str) -> str:
    try:
        query_params = getattr(request, "query_params", {})
    except Exception:
        return ""
    if not isinstance(query_params, dict):
        try:
            value = query_params.get(key)
        except Exception:
            return ""
    else:
        value = query_params.get(key)
    return str(value or "").strip()


def _extract_iss(payload: dict[str, Any]) -> str:
    value = _extract_payload_value(payload, "iss")
    if isinstance(value, str):
        return value.strip()
    return ""


def _extract_required_type(payload: dict[str, Any]) -> str:
    value = _extract_payload_value(payload, "type")
    if isinstance(value, str):
        return value.strip()
    return ""


def _require_epoch_seconds(payload: dict[str, Any], key: str) -> int:
    raw = _extract_payload_value(payload, key)
    if raw in (None, ""):
        raise HTTPException(status_code=400, detail=f"{key} is required in DIDComm payload")
    try:
        return int(str(raw).strip())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"{key} must be an integer epoch seconds value") from exc


def _to_lower_token(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = str(token).strip().split(".")
    if len(parts) < 2:
        raise ValueError("token is not JWT-like")
    payload_b64 = parts[1].strip()
    if not payload_b64:
        raise ValueError("token payload segment is empty")
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    payload = json.loads(decoded.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("token payload is not a JSON object")
    return payload


def _parse_token_claims(token: str, field_name: str, require_jwt: bool) -> dict[str, Any]:
    raw = str(token or "").strip()
    if not raw:
        return {}
    if raw.count(".") >= 2:
        try:
            return _decode_jwt_payload(raw)
        except Exception as exc:
            if require_jwt:
                raise HTTPException(status_code=401, detail=f"{field_name} is not a valid JWT payload") from exc
            return {}

    if require_jwt:
        raise HTTPException(status_code=401, detail=f"{field_name} must be a JWT in current auth mode")

    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _collect_claim_values(node: Any, keys: set[str], out: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and key.strip().lower() in keys and isinstance(value, str) and value.strip():
                out.add(value.strip().lower())
            _collect_claim_values(value, keys, out)
        return
    if isinstance(node, list):
        for item in node:
            _collect_claim_values(item, keys, out)


def _extract_device_token_from_iss(issuer: str) -> str:
    normalized = str(issuer or "").strip().lower()
    marker = ":device:"
    if marker not in normalized:
        return ""
    return normalized.split(marker, 1)[1].strip()


def _extract_bearer_token(authorization_header: str) -> str:
    raw = str(authorization_header or "").strip()
    if not raw:
        return ""
    prefix = "bearer "
    lowered = raw.lower()
    if lowered.startswith(prefix):
        return raw[len(prefix) :].strip()
    return ""


def _scope_is_satisfied(required_scope: str, available_scopes: set[str]) -> bool:
    required = str(required_scope or "").strip()
    if not required:
        return True
    available = {str(item or "").strip() for item in available_scopes if str(item or "").strip()}
    if required in available:
        return True

    if required == "dataconv.upload":
        return any(item.endswith("/_upload") for item in available)
    if required == "dataconv.read":
        return any(item.endswith("/_search") for item in available)

    if required.endswith("/_upload") and "dataconv.upload" in available:
        return True
    if required.endswith("/_search") and "dataconv.read" in available:
        return True

    return any(_scope_pattern_matches(required, item) for item in available)


def _enforce_auth_context(
    payload: dict[str, Any],
    settings: Any,
    authorization_header: str = "",
    *,
    require_token: bool = False,
    required_scopes: set[str] | None = None,
    expected_organization: str = "",
) -> None:
    demo_mode = bool(getattr(settings, "demo_mode", True))
    bearer_token = _extract_bearer_token(authorization_header)

    if bearer_token:
        try:
            session_claims = validate_session_access_token(bearer_token, settings)
            token_organization = str(session_claims.get("organization") or "").strip().lower()
            required_organization = str(expected_organization or "").strip().lower()
            if required_organization and token_organization != required_organization:
                raise HTTPException(status_code=403, detail="Bearer token organization does not match tenant")
            if required_scopes and not demo_mode:
                available = {item for item in str(session_claims.get("scope") or "").split(" ") if item}
                available.update({item for item in session_claims.get("scopes", []) if isinstance(item, str) and item})
                missing = sorted(scope for scope in required_scopes if not _scope_is_satisfied(scope, available))
                if missing:
                    raise HTTPException(status_code=403, detail=f"insufficient scope: missing {missing[0]}")
            return
        except HTTPException:
            if not demo_mode:
                raise
        except Exception:
            if not demo_mode:
                raise HTTPException(status_code=401, detail="invalid or expired Bearer token")

    if not demo_mode:
        raise HTTPException(status_code=401, detail="Bearer token required")

    if demo_mode:
        # TODO(auth-cleanup): reading id_token/vp_token from the DIDComm body is a demo-mode
        # convenience that pre-dates the /exchange endpoint. In production the Bearer header is
        # the sole credential carrier — these fields are NOT part of the DIDComm contract.
        # Once the SDK stops embedding them in the request body, remove this block and rely
        # exclusively on bearer_token (already extracted above) for subject identity.
        # Coordinate removal with a SDK minor release bump (breaking change for DEMO_MODE demos).
        id_token = str(_extract_payload_value(payload, "id_token") or _extract_payload_value(payload, "idToken") or "").strip()
        if not id_token:
            id_token = bearer_token
        vp_token = str(_extract_payload_value(payload, "vp_token") or _extract_payload_value(payload, "vpToken") or "").strip()
        issuer = _extract_iss(payload)
        subject_candidates: set[str] = set()
        if issuer:
            subject_candidates.add(issuer.strip().lower())
        device_candidates: set[str] = set()
        device_from_iss = _extract_device_token_from_iss(issuer)
        if device_from_iss:
            device_candidates.add(device_from_iss)
        id_claims = _parse_token_claims(id_token, "id_token", require_jwt=False)
        vp_claims = _parse_token_claims(vp_token, "vp_token", require_jwt=False)
        subject_keys = {"sub", "email", "upn", "preferred_username", "did", "iss", "employee_id", "employeeid", "username"}
        device_keys = {"device_id", "deviceid", "device_did", "did_device"}
        _collect_claim_values(id_claims, subject_keys, subject_candidates)
        _collect_claim_values(vp_claims, subject_keys, subject_candidates)
        _collect_claim_values(id_claims, device_keys, device_candidates)
        _collect_claim_values(vp_claims, device_keys, device_candidates)
    else:
        subject_candidates = set()
        device_candidates = set()

    disabled_subjects = {_to_lower_token(value) for value in getattr(settings, "auth_disabled_subjects", ()) if _to_lower_token(value)}
    disabled_devices = {_to_lower_token(value) for value in getattr(settings, "auth_disabled_devices", ()) if _to_lower_token(value)}

    blocked_subjects = sorted(subject_candidates & disabled_subjects)
    if blocked_subjects:
        raise HTTPException(status_code=403, detail=f"subject disabled or revoked: {blocked_subjects[0]}")

    blocked_devices = sorted(device_candidates & disabled_devices)
    if blocked_devices:
        raise HTTPException(status_code=403, detail=f"device disabled or revoked: {blocked_devices[0]}")


def _validate_public_iss(issuer: str) -> None:
    normalized = str(issuer or "").strip().lower()
    if not normalized.startswith("did:web:"):
        raise HTTPException(
            status_code=400,
            detail="iss must be a did:web identifier for this public API profile",
        )
    if ":employee:" not in normalized and ":system:" not in normalized:
        raise HTTPException(
            status_code=400,
            detail="iss must identify an employee or system actor (did:web ... :employee:... or :system:...)",
        )


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return default


def _merge_multipart_metadata(payload: dict[str, Any], form_data: Any) -> dict[str, Any]:
    merged = dict(payload or {})
    if form_data is None or not hasattr(form_data, "items"):
        return merged

    raw_meta: dict[str, Any] = {}
    for key, value in form_data.items():
        if key == "file":
            continue
        if hasattr(value, "filename"):
            continue
        raw_meta[str(key)] = value

    for container_key in ("metadata", "didcomm", "body", "payload"):
        candidate = raw_meta.get(container_key)
        if isinstance(candidate, str) and candidate.strip():
            try:
                parsed = json.loads(candidate)
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                raw_meta = {**parsed, **raw_meta}
                break

    for key, value in raw_meta.items():
        if key in {"file", "metadata", "didcomm", "body", "payload"}:
            continue
        if key not in merged or merged[key] in (None, ""):
            merged[key] = value
    return merged


def _resolve_manufacturer_and_version(
    manufacturer_raw: str,
    manufacturer_version_raw: str = "",
) -> tuple[str, str]:
    token = str(manufacturer_raw or "").strip().lower()
    if not token:
        return ("", "")

    inferred_name = token
    inferred_version = ""
    if "-v" in token:
        base, suffix = token.rsplit("-v", 1)
        base = base.strip()
        suffix = suffix.strip()
        if base and suffix:
            inferred_name = base
            inferred_version = f"v{suffix}"

    explicit_version = str(manufacturer_version_raw or "").strip().lower()
    if explicit_version and not explicit_version.startswith("v"):
        explicit_version = f"v{explicit_version}"

    if inferred_version and explicit_version and inferred_version != explicit_version:
        raise HTTPException(
            status_code=400,
            detail="software version mismatch between softwareId token and softwareVersion field",
        )
    return (inferred_name, inferred_version or explicit_version)


def _compose_software_id_token(manufacturer: str, manufacturer_version: str) -> str:
    name = str(manufacturer or "").strip()
    version = str(manufacturer_version or "").strip()
    if not name:
        return ""
    if not version:
        return name
    return f"{name}-{version}"


def _extract_software_token_from_entry(entry: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(entry, dict):
        return ("", "")
    software_id = str(entry.get("softwareId") or "").strip()
    software_version = str(entry.get("softwareVersion") or "").strip()
    return (software_id, software_version)


def _load_json_blob(blob_store: Any, refs: list[str]) -> dict[str, Any] | None:
    for ref in refs:
        text = str(ref or "").strip()
        if not text:
            continue
        try:
            raw_bytes = blob_store.get_bytes(text)
            parsed = json.loads(raw_bytes.decode("utf-8"))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return None


def _output_ref_candidates(job: Any, artifact_name: str) -> list[str]:
    candidates: list[str] = []
    result_ref = str(getattr(job, "result_ref", "") or "").strip()
    if result_ref:
        if result_ref.endswith("summary.json"):
            base = result_ref[: -len("summary.json")]
            candidates.append(f"{base}{artifact_name}")
        elif artifact_name == "summary.json":
            candidates.append(result_ref)
    job_id = str(getattr(job, "job_id", "") or "").strip()
    if job_id:
        candidates.append(f"jobs/{job_id}/{artifact_name}")
    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def _summary_diagnostics_es(summary: dict[str, Any], job: Any) -> str:
    records_total = int(summary.get("recordsTotal") or summary.get("totalRecords") or 0)
    log_composition = bool(summary.get("logComposition", False))

    resource_type_counts: dict[str, int] = {}
    raw_counts = summary.get("resourceTypeCounts")
    if isinstance(raw_counts, dict):
        for key, value in raw_counts.items():
            resource_type = str(key or "").strip()
            if not resource_type:
                continue
            try:
                resource_type_counts[resource_type] = int(value or 0)
            except (TypeError, ValueError):
                continue

    if not resource_type_counts:
        fallback_counts = {
            "Subject": int(summary.get("subjectsTotal") or 0),
            "DocumentReference": int(summary.get("documentReferenceEntries") or 0),
            "Encounter": int(summary.get("encounterEntries") or 0),
            "Composition": int(summary.get("compositionEntries") or 0),
            "RelatedPerson": int(summary.get("relatedPersonEntries") or 0),
            "OperationOutcome": int(summary.get("operationOutcomeEntries") or 0),
        }
        resource_type_counts = {
            key: count for key, count in fallback_counts.items() if int(count) > 0 or key == "Encounter"
        }

    parts: list[str] = []
    if records_total > 0:
        parts.append(f"Se han procesado {records_total} registros.")

    ordered_resource_types = sorted(resource_type_counts.keys(), key=lambda name: (0 if name == "Subject" else 1, name))
    for resource_type in ordered_resource_types:
        if resource_type == "Composition" and not log_composition:
            continue
        count = int(resource_type_counts.get(resource_type) or 0)
        parts.append(f"Se han generado {count} {resource_type}.")

    started_at = _parse_iso_utc(str(getattr(job, "started_at", "") or ""))
    finished_at = _parse_iso_utc(str(getattr(job, "finished_at", "") or ""))
    created_at = _parse_iso_utc(str(getattr(job, "created_at", "") or ""))
    started_or_created = started_at or created_at
    if started_or_created is not None and finished_at is not None:
        duration_seconds = max(int((finished_at - started_or_created).total_seconds()), 0)
        parts.append(f"La operación fue procesada en {duration_seconds} segundos.")

    return " ".join(parts).strip()


def _job_poll_response(
    job: Any,
    response: Response | None = None,
    blob_store: Any | None = None,
    queue_position: int | None = None,
    service_iss: str = "",
    audience_did: str = "",
) -> dict[str, Any]:
    diagnostics = f"Job status: {job.status}"
    if job.error:
        diagnostics = f"{diagnostics}. {job.error}"
    http_status = 202 if job.status in {"queued", "running"} else 200
    if response is not None:
        response.status_code = http_status
        if http_status == 202:
            response.headers["Retry-After"] = "5"

    severity = "information"
    issue_code = "processing"
    item_status = "202"
    output_resource: dict[str, Any] | None = None
    resolved_iss = str(service_iss or "").strip()
    resolved_aud = str(audience_did or "").strip()
    attachments: list[dict[str, Any]] | None = None

    if job.status == "succeeded" and blob_store is not None:
        summary = _load_json_blob(blob_store, _output_ref_candidates(job, "summary.json"))
        composition = _load_json_blob(blob_store, _output_ref_candidates(job, "composition-message.json"))
        if isinstance(summary, dict):
            summary_diagnostics = _summary_diagnostics_es(summary, job)
            if summary_diagnostics:
                diagnostics = f"{diagnostics}. {summary_diagnostics}"
            adapter_report = summary.get("adapterReport")
            if isinstance(adapter_report, dict):
                dropped_no_subject_id = int(adapter_report.get("recordsDroppedNoSubjectId") or 0)
                if dropped_no_subject_id > 0:
                    diagnostics = (
                        f"{diagnostics}. Dropped {dropped_no_subject_id} record(s) due to missing "
                        "subject_id values or an incorrect schemaConfig.fieldMap.subject_id mapping."
                    )
                dropped_missing_loinc = int(adapter_report.get("recordsDroppedMissingLoincMapping") or 0)
                if dropped_missing_loinc > 0:
                    missing = adapter_report.get("missingLoincBySectionFamily")
                    samples = ""
                    if isinstance(missing, dict) and missing:
                        top_items = sorted(
                            (
                                (str(key).strip(), int(value or 0))
                                for key, value in missing.items()
                                if str(key).strip()
                            ),
                            key=lambda item: (-item[1], item[0]),
                        )[:5]
                        if top_items:
                            samples = ", ".join(f"{key}({count})" for key, count in top_items)
                    row_numbers = ""
                    row_issues = adapter_report.get("rowIssues")
                    if isinstance(row_issues, list) and row_issues:
                        rows = [
                            int(item.get("rowNumber") or 0)
                            for item in row_issues
                            if isinstance(item, dict)
                            and str(item.get("code", "")).strip() == "missing-loinc-mapping"
                            and int(item.get("rowNumber") or 0) > 0
                        ]
                        if rows:
                            unique_rows = sorted(set(rows))[:10]
                            row_numbers = ", ".join(str(value) for value in unique_rows)
                    diagnostics = (
                        f"{diagnostics}. Dropped {dropped_missing_loinc} record(s) due to missing "
                        "LOINC mapping for section:family."
                    )
                    if samples:
                        diagnostics = f"{diagnostics} Missing: {samples}."
                    if row_numbers:
                        diagnostics = f"{diagnostics} Rows: {row_numbers}."
        severity = "information"
        issue_code = "informational"
        item_status = "200"
        if isinstance(composition, dict):
            resolved_iss = str(composition.get("iss") or resolved_iss).strip()
            resolved_aud = str(composition.get("aud") or resolved_aud).strip()
            raw_body = composition.get("body")
            if isinstance(raw_body, dict):
                output_resource = raw_body
            raw_attachments = composition.get("attachments")
            if isinstance(raw_attachments, list):
                attachments = [item for item in raw_attachments if isinstance(item, dict)]
    elif job.status == "failed":
        severity = "error"
        issue_code = "exception"
        item_status = "500"

    outcome = _op_outcome(
        severity=severity,
        code=issue_code,
        diagnostics=diagnostics,
    )
    entry_response: dict[str, Any] = {
        "status": item_status,
        "outcome": outcome,
    }
    if job.status == "queued" and isinstance(queue_position, int) and queue_position > 0:
        entry_response["queuePosition"] = int(queue_position)

    entry: dict[str, Any] = {
        "type": "ConversionResult",
        "response": entry_response,
    }
    if isinstance(output_resource, dict):
        entry["resource"] = output_resource

    issued_at = int(datetime.now(timezone.utc).timestamp())
    payload: dict[str, Any] = {
        "jti": str(uuid.uuid4()),
        "thid": str(getattr(job, "thid", "") or "").strip(),
        "type": DIDCOMM_DEFAULT_MESSAGE_TYPE,
        "iss": resolved_iss,
        "aud": resolved_aud,
        "iat": issued_at,
        "exp": issued_at + 300,
        "body": {
            "resourceType": "Bundle",
            "type": "batch-response",
            "issues": outcome,
            "data": [entry],
            "total": 1,
        },
    }
    if attachments:
        payload["attachments"] = attachments
    return payload
