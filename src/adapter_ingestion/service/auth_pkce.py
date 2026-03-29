from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()

# tenant-scoped in-memory registries for local/dev profile
DCR_REGISTRY: dict[str, dict[str, Any]] = {}
PKCE_CODES: dict[str, dict[str, Any]] = {}
TOKENS: dict[str, dict[str, Any]] = {}
AUTH_JOBS: dict[str, dict[str, Any]] = {}


class DidcommAuthRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    thid: str | None = None
    type: str | None = None
    iat: int | None = None
    exp: int | None = None
    body: dict[str, Any] = Field(default_factory=dict)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


def _tenant_key(*, tenant_id: str, client_id: str) -> str:
    return f"{tenant_id.strip().lower()}::{client_id.strip()}"


def _api_key_hash(raw_api_key: str) -> str:
    token = str(raw_api_key or "").strip()
    if not token:
        return ""
    return hashlib.sha256(token.encode("utf-8")).hexdigest().lower()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _jwt_none(payload: dict[str, Any]) -> str:
    header = {"alg": "none", "typ": "JWT"}
    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{header_b64}.{payload_b64}."


def _pkce_s256_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return _b64url(digest)


def _enqueue_job(
    *,
    action: str,
    tenant_id: str,
    jurisdiction: str,
    sector: str,
    request_payload: DidcommAuthRequest,
    result_payload: dict[str, Any],
) -> str:
    thid = str(request_payload.thid or "").strip() or f"thid-{uuid.uuid4()}"
    AUTH_JOBS[thid] = {
        "status": "completed",
        "action": action,
        "tenant_id": tenant_id,
        "jurisdiction": jurisdiction,
        "sector": sector,
        "result": result_payload,
        "updated_at": int(time.time()),
    }
    return thid


def _set_async_headers(
    response: Response,
    *,
    tenant_id: str,
    jurisdiction: str,
    sector: str,
    action: str,
    thid: str,
) -> None:
    response.status_code = 202
    response.headers["Location"] = (
        f"/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/identity/auth/{action}-response?thid={thid}"
    )
    response.headers["Retry-After"] = "1"


def _poll_job(*, thid: str, action: str, response: Response) -> dict[str, Any]:
    record = AUTH_JOBS.get(thid)
    if not record or str(record.get("action")) != action:
        raise HTTPException(status_code=404, detail="thid not found")
    status = str(record.get("status") or "")
    if status != "completed":
        response.status_code = 202
        response.headers["Retry-After"] = "1"
        return {"thid": thid, "status": "pending"}
    response.status_code = 200
    return {"thid": thid, **(record.get("result") or {})}


def list_tenant_bindings(*, tenant_id: str) -> list[dict[str, Any]]:
    tenant_token = str(tenant_id or "").strip().lower()
    rows: list[dict[str, Any]] = []
    for item in DCR_REGISTRY.values():
        if not isinstance(item, dict):
            continue
        if str(item.get("tenant_id") or "").strip().lower() != tenant_token:
            continue
        rows.append(dict(item))
    return rows


def _require_didcomm_meta_for_plain(payload: DidcommAuthRequest) -> None:
    # DIDComm-plain bootstrap profile: controller signing key in meta.jws.protected.jwk
    meta = payload.meta if isinstance(payload.meta, dict) else {}
    jws = meta.get("jws") if isinstance(meta.get("jws"), dict) else {}
    protected = jws.get("protected") if isinstance(jws.get("protected"), dict) else {}
    if not isinstance(protected.get("jwk"), dict):
        raise HTTPException(status_code=400, detail="meta.jws.protected.jwk is required for didcomm-plain auth flow")


def _process_dcr(*, tenant_id: str, payload: DidcommAuthRequest) -> dict[str, Any]:
    _require_didcomm_meta_for_plain(payload)
    body = payload.body if isinstance(payload.body, dict) else {}
    raw = payload.model_dump()
    client_id = str(raw.get("client_id") or body.get("client_id") or "").strip()
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id is required")
    # Backend SDK profile: DCR client_id is the API key used for policy binding.
    api_key_hash = _api_key_hash(client_id)
    key = _tenant_key(tenant_id=tenant_id, client_id=client_id)
    meta = payload.meta if isinstance(payload.meta, dict) else {}
    controller_jwk = (
        meta.get("jws", {})
        .get("protected", {})
        .get("jwk")
        if isinstance(meta.get("jws"), dict)
        else None
    )
    DCR_REGISTRY[key] = {
        "tenant_id": tenant_id.strip().lower(),
        "client_id": client_id,
        "api_key_hash": api_key_hash,
        "controller_jwk": controller_jwk,
        "metadata": body,
        "attachments": payload.attachments,
        "binding_status": "bound",
        "bound_at": int(time.time()),
        "device": raw.get("device") if isinstance(raw.get("device"), dict) else {},
    }
    return {
        "status": "ok",
        "action": "_dcr",
        "bindingStatus": "bound",
        "tenant_id": tenant_id,
        "client_id": client_id,
    }


def _process_code(*, tenant_id: str, payload: DidcommAuthRequest) -> dict[str, Any]:
    _require_didcomm_meta_for_plain(payload)
    body = payload.body if isinstance(payload.body, dict) else {}
    raw = payload.model_dump()
    api_key = str(raw.get("client_id") or body.get("client_id") or "").strip()
    code_challenge = str(raw.get("code_challenge") or body.get("code_challenge") or "").strip()
    method = str(raw.get("code_challenge_method") or body.get("code_challenge_method") or "S256").strip().upper()
    if method != "S256":
        raise HTTPException(status_code=400, detail="code_challenge_method must be S256")
    if not api_key or not code_challenge:
        raise HTTPException(status_code=400, detail="client_id and code_challenge are required")
    key = _tenant_key(tenant_id=tenant_id, client_id=api_key)
    if key not in DCR_REGISTRY:
        raise HTTPException(status_code=401, detail="client not registered via _dcr")

    code = str(uuid.uuid4())
    expires_at = int(time.time()) + 300
    PKCE_CODES[code] = {
        "tenant_id": tenant_id.strip().lower(),
        "client_id": api_key,
        "code_challenge": code_challenge,
        "code_challenge_method": method,
        "expires_at": expires_at,
    }
    return {"status": "ok", "action": "_code", "code": code, "expires_in": 300}


def _process_token(*, tenant_id: str, payload: DidcommAuthRequest) -> dict[str, Any]:
    _require_didcomm_meta_for_plain(payload)
    body = payload.body if isinstance(payload.body, dict) else {}
    raw = payload.model_dump()
    api_key = str(raw.get("client_id") or body.get("client_id") or "").strip()
    code = str(raw.get("code") or body.get("code") or "").strip()
    code_verifier = str(raw.get("code_verifier") or body.get("code_verifier") or "").strip()
    if not api_key or not code or not code_verifier:
        raise HTTPException(status_code=400, detail="client_id, code and code_verifier are required")

    record = PKCE_CODES.get(code)
    if not record:
        raise HTTPException(status_code=401, detail="invalid code")
    if int(record.get("expires_at") or 0) < int(time.time()):
        raise HTTPException(status_code=401, detail="code expired")
    if str(record.get("tenant_id") or "") != tenant_id.strip().lower():
        raise HTTPException(status_code=401, detail="code tenant mismatch")
    if str(record.get("client_id") or "") != api_key:
        raise HTTPException(status_code=401, detail="code client mismatch")

    expected = _pkce_s256_challenge(code_verifier)
    if expected != str(record.get("code_challenge") or ""):
        raise HTTPException(status_code=401, detail="invalid code_verifier")

    expires_in = 300
    now = int(time.time())
    id_token = _jwt_none(
        {
            "iss": "https://identity.dataconv.local",
            "sub": f"client:{api_key}",
            "aud": "dataconv",
            "iat": now,
            "exp": now + expires_in,
            "tenant": tenant_id.strip().lower(),
        }
    )
    TOKENS[id_token] = {"tenant_id": tenant_id.strip().lower(), "client_id": api_key, "expires_at": now + expires_in}
    return {
        "status": "ok",
        "action": "_token",
        "id_token": id_token,
        "token_type": "urn:ietf:params:oauth:token-type:id_token",
        "expires_in": expires_in,
    }


@router.post(
    "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/identity/auth/_dcr",
    tags=["2.1 Identity Auth DCR"],
    summary="Submit DCR job (async)",
)
def submit_dcr(
    tenant_id: str,
    jurisdiction: str,
    sector: str,
    request: Request,
    response: Response,
    body: DidcommAuthRequest,
) -> None:
    payload = body.model_dump()
    payload["device"] = {
        "ip": str(getattr(getattr(request, "client", None), "host", "") or ""),
        "userAgent": str(request.headers.get("user-agent", "") or ""),
        "os": str(request.headers.get("x-device-os", "") or ""),
        "platform": str(request.headers.get("x-device-platform", "") or ""),
        "sdkVersion": str(request.headers.get("x-sdk-version", "") or ""),
    }
    body = DidcommAuthRequest.model_validate(payload)
    result = _process_dcr(tenant_id=tenant_id, payload=body)
    thid = _enqueue_job(
        action="_dcr",
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        sector=sector,
        request_payload=body,
        result_payload=result,
    )
    _set_async_headers(
        response,
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        sector=sector,
        action="_dcr",
        thid=thid,
    )
    return None


@router.post(
    "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/identity/auth/_dcr-response",
    tags=["2.1 Identity Auth DCR"],
    summary="Poll DCR job status/result",
)
def poll_dcr(response: Response, thid: str = Query(...)) -> dict[str, Any]:
    return _poll_job(thid=thid, action="_dcr", response=response)


@router.post(
    "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/identity/auth/_code",
    tags=["2.2 Identity Auth PKCE Code"],
    summary="Submit PKCE code job (async)",
)
def submit_code(
    tenant_id: str,
    jurisdiction: str,
    sector: str,
    response: Response,
    body: DidcommAuthRequest,
) -> None:
    result = _process_code(tenant_id=tenant_id, payload=body)
    thid = _enqueue_job(
        action="_code",
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        sector=sector,
        request_payload=body,
        result_payload=result,
    )
    _set_async_headers(
        response,
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        sector=sector,
        action="_code",
        thid=thid,
    )
    return None


@router.post(
    "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/identity/auth/_code-response",
    tags=["2.2 Identity Auth PKCE Code"],
    summary="Poll PKCE code job status/result",
)
def poll_code(response: Response, thid: str = Query(...)) -> dict[str, Any]:
    return _poll_job(thid=thid, action="_code", response=response)


@router.post(
    "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/identity/auth/_token",
    tags=["2.3 Identity Auth PKCE Token"],
    summary="Submit PKCE token job (async)",
)
def submit_token(
    tenant_id: str,
    jurisdiction: str,
    sector: str,
    response: Response,
    body: DidcommAuthRequest,
) -> None:
    result = _process_token(tenant_id=tenant_id, payload=body)
    thid = _enqueue_job(
        action="_token",
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        sector=sector,
        request_payload=body,
        result_payload=result,
    )
    _set_async_headers(
        response,
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        sector=sector,
        action="_token",
        thid=thid,
    )
    return None


@router.post(
    "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/identity/auth/_token-response",
    tags=["2.3 Identity Auth PKCE Token"],
    summary="Poll PKCE token job status/result",
)
def poll_token(response: Response, thid: str = Query(...)) -> dict[str, Any]:
    return _poll_job(thid=thid, action="_token", response=response)
