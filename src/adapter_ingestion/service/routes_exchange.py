from __future__ import annotations

from typing import Any

from .api_support import Body, HTTPException, Request


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
        tags=["OAuth Token Exchange"],
        summary="Exchange OIDC id_token + VP for DataConv access token",
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
        tags=["OAuth Token Exchange"],
        summary="OAuth-compatible token exchange endpoint",
    )
    async def oauth_token_exchange(request: Request, body: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        payload = await _read_exchange_payload(request, body)
        audience = _build_exchange_audience(request)
        try:
            result = exchange_manager.exchange(payload, audience=audience)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return exchange_manager.as_response(result)
