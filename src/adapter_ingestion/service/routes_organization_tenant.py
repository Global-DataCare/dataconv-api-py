# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
from typing import Any

from .api_support import Body, HTTPException


def register_organization_tenant_routes(app: Any, *, activation_manager: Any) -> None:
    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/organization/research/auth/_exchange",
        tags=["1.3 Organization Tenant Activation"],
        summary="Exchange a current ICA controller proof for a tenant-bound research upload token",
        description=(
            "Requires the exact DataConv tenant to be active for the current network, sector and "
            "jurisdiction. Call the idempotent organization/tenant/_activate route first when "
            "refreshing an existing portal tenant."
        ),
    )
    async def exchange_controller_research_upload_token(
        jurisdiction: str,
        sector: str,
        tenant_id: str,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                activation_manager.exchange_upload_token,
                tenant_id=tenant_id,
                jurisdiction=jurisdiction,
                sector=sector,
                id_token=str(body.get("id_token") or body.get("idToken") or "").strip(),
                vp_token=str(body.get("vp_token") or body.get("vpToken") or "").strip(),
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/organization/tenant/_activate",
        tags=["1.3 Organization Tenant Activation"],
        summary="Activate a DataConv tenant from OIDC and ICA controller proof",
    )
    async def activate_organization_tenant(
        jurisdiction: str,
        sector: str,
        tenant_id: str,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                activation_manager.activate,
                tenant_id=tenant_id,
                jurisdiction=jurisdiction,
                sector=sector,
                id_token=str(body.get("id_token") or body.get("idToken") or "").strip(),
                vp_token=str(body.get("vp_token") or body.get("vpToken") or "").strip(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
