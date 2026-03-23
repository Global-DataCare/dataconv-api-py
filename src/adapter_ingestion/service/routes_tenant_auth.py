from __future__ import annotations

from typing import Any

from .api_support import Body, Path, Request


def register_tenant_auth_routes(app, *, tenant_api_key_manager) -> None:  # type: ignore[no-untyped-def]
    def _auth_header(request: Request | None) -> str:
        if request is None:
            return ""
        return str(request.headers.get("authorization", "") or "")

    @app.post(
        "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/api-key/org.schema/action/_create",
        tags=["1.3 Tenant Auth API Keys"],
        summary="Create tenant-scoped API key policy",
        description=(
            "Creates an API key bound to tenant + email with granular scopes and optional ODRL payload. "
            "The request and response use the canonical `data[].resource` envelope.\n\n"
            "Requires Bearer token issued by `/exchange` with scope `dataconv.tenant.keys.manage` and"
            " `organization` matching `{tenant_id}`."
        ),
    )
    async def create_tenant_api_key(
        jurisdiction: str,
        sector: str,
        tenant_id: str = Path(description="Stable organization identifier (`taxId` / `VAT`)."),
        request: Request = None,  # type: ignore[assignment]
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        payload = dict(body) if isinstance(body, dict) else {}
        return tenant_api_key_manager.create_api_key(
            tenant_id=tenant_id,
            authorization_header=_auth_header(request),
            payload=payload,
        )

    @app.post(
        "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/api-key/org.schema/action/_disable",
        tags=["1.3 Tenant Auth API Keys"],
        summary="Disable tenant-scoped API key policy",
        description=(
            "Disables one or more API keys already provisioned for the tenant using the same `data[].resource` "
            "action envelope as `_create`. Each action must identify the target key by `identifier` (`keyId`) or "
            "`agent.email`.\n\n"
            "Requires Bearer token issued by `/exchange` with scope `dataconv.tenant.keys.manage` and"
            " `organization` matching `{tenant_id}`."
        ),
    )
    async def disable_tenant_api_key(
        jurisdiction: str,
        sector: str,
        tenant_id: str = Path(description="Stable organization identifier (`taxId` / `VAT`)."),
        request: Request = None,  # type: ignore[assignment]
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        payload = dict(body) if isinstance(body, dict) else {}
        return tenant_api_key_manager.disable_api_key(
            tenant_id=tenant_id,
            authorization_header=_auth_header(request),
            payload=payload,
        )

    @app.post(
        "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/api-key/org.schema/action/_remove",
        tags=["1.3 Tenant Auth API Keys"],
        summary="Remove tenant-scoped API key policy",
        description=(
            "Removes one or more API keys from the tenant registry using the same `data[].resource` action envelope "
            "as `_create`. Each action must identify the target key by `identifier` (`keyId`) or `agent.email`.\n\n"
            "Requires Bearer token issued by `/exchange` with scope `dataconv.tenant.keys.manage` and"
            " `organization` matching `{tenant_id}`."
        ),
    )
    async def remove_tenant_api_key(
        jurisdiction: str,
        sector: str,
        tenant_id: str = Path(description="Stable organization identifier (`taxId` / `VAT`)."),
        request: Request = None,  # type: ignore[assignment]
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        payload = dict(body) if isinstance(body, dict) else {}
        return tenant_api_key_manager.remove_api_key(
            tenant_id=tenant_id,
            authorization_header=_auth_header(request),
            payload=payload,
        )
