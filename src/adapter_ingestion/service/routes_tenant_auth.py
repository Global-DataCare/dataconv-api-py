from __future__ import annotations

from typing import Any

from .api_support import Body, HTTPException, Request
from .auth_exchange import validate_session_access_token
from .auth_pkce import list_tenant_bindings


def register_tenant_auth_routes(app, *, tenant_api_key_manager, settings) -> None:  # type: ignore[no-untyped-def]
    def _auth_header(request: Request | None) -> str:
        if request is None:
            return ""
        return str(request.headers.get("authorization", "") or "")

    def _tenant_from_bearer(auth_header: str) -> str:
        raw_header = str(auth_header or "").strip()
        if not raw_header.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Bearer token required")
        token = raw_header[7:].strip()
        if not token:
            raise HTTPException(status_code=401, detail="Bearer token required")
        try:
            claims = validate_session_access_token(token, settings)
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"invalid Bearer token: {exc}") from exc
        tenant_id = str(claims.get("organization") or "").strip().lower()
        if not tenant_id:
            raise HTTPException(status_code=403, detail="token organization claim is required")
        return tenant_id

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/api-key/org.schema/action/_create",
        tags=["1.2 Controller API Key Provisioning"],
        summary="Create API key policy for controller organization",
        description=(
            "Creates an API key bound to organization + email with granular scopes and optional ODRL payload. "
            "The request and response use the canonical `data[].resource` envelope.\n\n"
            "Organization is resolved from Bearer token claim `organization`."
        ),
    )
    async def create_tenant_api_key(
        jurisdiction: str,
        sector: str,
        request: Request = None,  # type: ignore[assignment]
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        payload = dict(body) if isinstance(body, dict) else {}
        auth_header = _auth_header(request)
        tenant_id = _tenant_from_bearer(auth_header)
        return tenant_api_key_manager.create_api_key(
            tenant_id=tenant_id,
            authorization_header=auth_header,
            payload=payload,
        )

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/api-key/org.schema/action/_disable",
        tags=["1.2 Controller API Key Provisioning"],
        summary="Disable API key policy for controller organization",
        description=(
            "Disables one or more API keys already provisioned for the organization using the same `data[].resource` "
            "action envelope as `_create`. Each action must identify the target key by `identifier` (`keyId`) or "
            "`agent.email`.\n\n"
            "Organization is resolved from Bearer token claim `organization`."
        ),
    )
    async def disable_tenant_api_key(
        jurisdiction: str,
        sector: str,
        request: Request = None,  # type: ignore[assignment]
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        payload = dict(body) if isinstance(body, dict) else {}
        auth_header = _auth_header(request)
        tenant_id = _tenant_from_bearer(auth_header)
        return tenant_api_key_manager.disable_api_key(
            tenant_id=tenant_id,
            authorization_header=auth_header,
            payload=payload,
        )

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/api-key/org.schema/action/_remove",
        tags=["1.2 Controller API Key Provisioning"],
        summary="Remove API key policy for controller organization",
        description=(
            "Removes one or more API keys from the organization registry using the same `data[].resource` action envelope "
            "as `_create`. Each action must identify the target key by `identifier` (`keyId`) or `agent.email`.\n\n"
            "Organization is resolved from Bearer token claim `organization`."
        ),
    )
    async def remove_tenant_api_key(
        jurisdiction: str,
        sector: str,
        request: Request = None,  # type: ignore[assignment]
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        payload = dict(body) if isinstance(body, dict) else {}
        auth_header = _auth_header(request)
        tenant_id = _tenant_from_bearer(auth_header)
        return tenant_api_key_manager.remove_api_key(
            tenant_id=tenant_id,
            authorization_header=auth_header,
            payload=payload,
        )

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/api-key/org.schema/action/_search",
        tags=["1.2 Controller API Key Provisioning"],
        summary="List API keys and DCR bindings for controller organization",
        description=(
            "Returns API key registry entries for the organization resolved from Bearer token, enriched with "
            "DCR bindings (`client_id`, `controller_jwk`, `device` metadata) matched by api key hash."
        ),
    )
    async def search_tenant_api_keys(
        jurisdiction: str,
        sector: str,
        request: Request = None,  # type: ignore[assignment]
    ) -> dict[str, Any]:
        auth_header = _auth_header(request)
        tenant_id = _tenant_from_bearer(auth_header)
        listing = tenant_api_key_manager.list_api_keys(
            tenant_id=tenant_id,
            authorization_header=auth_header,
        )
        bindings = list_tenant_bindings(tenant_id=tenant_id)
        by_hash: dict[str, list[dict[str, Any]]] = {}
        for item in bindings:
            key_hash = str(item.get("api_key_hash") or "").strip().lower()
            if not key_hash:
                continue
            by_hash.setdefault(key_hash, []).append(
                {
                    "clientId": str(item.get("client_id") or ""),
                    "bindingStatus": str(item.get("binding_status") or "bound"),
                    "boundAt": int(item.get("bound_at") or 0),
                    "controllerPublicKeyJwk": item.get("controller_jwk") if isinstance(item.get("controller_jwk"), dict) else {},
                    "device": item.get("device") if isinstance(item.get("device"), dict) else {},
                }
            )

        data = listing.get("data") if isinstance(listing.get("data"), list) else []
        enriched: list[dict[str, Any]] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            resource = entry.get("resource") if isinstance(entry.get("resource"), dict) else {}
            key_hash = str(resource.get("keyHash") or "").strip().lower()
            entry_out = dict(entry)
            entry_out["bindings"] = by_hash.get(key_hash, [])
            enriched.append(entry_out)
        return {"data": enriched}
