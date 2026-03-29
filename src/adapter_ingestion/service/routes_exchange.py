from __future__ import annotations

import time
import uuid
from typing import Any

from .api_support import Body, HTTPException, Request, Response

EXCHANGE_JOBS: dict[str, dict[str, Any]] = {}


def _build_exchange_audience(request: Request) -> str:
    try:
        return str(request.url_for("exchange_token")).strip()
    except Exception:
        base = str(request.base_url).rstrip("/")
        return f"{base}/exchange"


async def _read_exchange_payload(request: Request, body: Any) -> dict[str, Any]:
    if isinstance(body, dict):
        payload = dict(body)
    else:
        payload = {}
    try:
        form = await request.form()
    except Exception:
        form = None
    if form is not None and len(form) > 0:
        payload = {str(key): value for key, value in form.items()}

    header_api_key = str(request.headers.get("x-api-key", "") or "").strip()
    if header_api_key and not payload.get("api_key"):
        payload["api_key"] = header_api_key
    return payload


def register_exchange_routes(app, *, exchange_manager) -> None:  # type: ignore[no-untyped-def]
    @app.post(
        "/exchange",
        tags=["1.1 Controller Auth Exchange"],
        summary="Exchange OIDC id_token + VP for DataConv access token",
        include_in_schema=False,
    )
    async def exchange_token(request: Request, body: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        payload = await _read_exchange_payload(request, body)
        audience = _build_exchange_audience(request)
        try:
            result = exchange_manager.exchange(payload, audience=audience)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return exchange_manager.as_response(result)

    @app.post(
        "/oauth/token",
        tags=["1.1 Controller Auth Exchange"],
        summary="OAuth-compatible token exchange endpoint",
        include_in_schema=False,
    )
    async def oauth_token_exchange(request: Request, body: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        payload = await _read_exchange_payload(request, body)
        audience = _build_exchange_audience(request)
        try:
            result = exchange_manager.exchange(payload, audience=audience)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return exchange_manager.as_response(result)

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/identity/auth/_exchange",
        tags=["2.4 Identity Auth Exchange"],
        summary="Submit exchange job (async)",
    )
    async def submit_tenant_exchange(
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        response: Response,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> None:
        payload = await _read_exchange_payload(request, body)
        didcomm_body = payload.get("body") if isinstance(payload.get("body"), dict) else None
        request_payload = didcomm_body if (didcomm_body is not None and len(didcomm_body) > 0) else payload
        audience = _build_exchange_audience(request)
        try:
            result = exchange_manager.exchange(request_payload, audience=audience)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        thid = str(payload.get("thid") or "").strip() or f"thid-{uuid.uuid4()}"
        EXCHANGE_JOBS[thid] = {
            "status": "completed",
            "tenant_id": str(tenant_id or "").strip().lower(),
            "jurisdiction": str(jurisdiction or "").strip(),
            "sector": str(sector or "").strip(),
            "result": exchange_manager.as_response(result),
            "updated_at": int(time.time()),
        }
        response.status_code = 202
        response.headers["Location"] = (
            f"/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/identity/auth/_exchange-response?thid={thid}"
        )
        response.headers["Retry-After"] = "1"
        return None

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/identity/auth/_exchange-response",
        tags=["2.4 Identity Auth Exchange"],
        summary="Poll exchange job status/result",
    )
    def poll_tenant_exchange(response: Response, thid: str) -> dict[str, Any]:
        job = EXCHANGE_JOBS.get(str(thid or "").strip())
        if not job:
            raise HTTPException(status_code=404, detail="thid not found")
        if str(job.get("status") or "") != "completed":
            response.status_code = 202
            response.headers["Retry-After"] = "1"
            return {"thid": thid, "status": "pending"}
        response.status_code = 200
        return {"thid": thid, **(job.get("result") or {})}

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/organization/dataspace/auth/_exchange",
        tags=["1.1 Controller Auth Exchange"],
        summary="Submit controller bootstrap exchange job (async)",
    )
    async def submit_controller_exchange(
        jurisdiction: str,
        sector: str,
        response: Response,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> None:
        payload = await _read_exchange_payload(request, body)
        didcomm_body = payload.get("body") if isinstance(payload.get("body"), dict) else None
        request_payload = didcomm_body if (didcomm_body is not None and len(didcomm_body) > 0) else payload
        audience = _build_exchange_audience(request)
        try:
            result = exchange_manager.exchange(request_payload, audience=audience)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        thid = str(payload.get("thid") or "").strip() or f"thid-{uuid.uuid4()}"
        EXCHANGE_JOBS[thid] = {
            "status": "completed",
            "tenant_id": str((exchange_manager.as_response(result) or {}).get("organization") or "").strip().lower(),
            "jurisdiction": str(jurisdiction or "").strip(),
            "sector": str(sector or "").strip(),
            "result": exchange_manager.as_response(result),
            "updated_at": int(time.time()),
        }
        response.status_code = 202
        response.headers["Location"] = (
            f"/publisher/cds-{jurisdiction}/v1/{sector}/organization/dataspace/auth/_exchange-response?thid={thid}"
        )
        response.headers["Retry-After"] = "1"
        return None

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/organization/dataspace/auth/_exchange-response",
        tags=["1.1 Controller Auth Exchange"],
        summary="Poll controller bootstrap exchange job status/result",
    )
    def poll_controller_exchange(response: Response, thid: str) -> dict[str, Any]:
        job = EXCHANGE_JOBS.get(str(thid or "").strip())
        if not job:
            raise HTTPException(status_code=404, detail="thid not found")
        if str(job.get("status") or "") != "completed":
            response.status_code = 202
            response.headers["Retry-After"] = "1"
            return {"thid": thid, "status": "pending"}
        response.status_code = 200
        return {"thid": thid, **(job.get("result") or {})}
