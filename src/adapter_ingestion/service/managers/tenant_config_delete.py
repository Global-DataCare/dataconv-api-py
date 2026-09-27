# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from ..api_support import HTTPException, _enforce_auth_context, _enforce_supported_scope
from .dependencies import ApiManagerDependencies


class TenantConfigDeleteManager:
    """Delete one exact tenant-owned adapter configuration with controller authority."""

    def __init__(self, deps: ApiManagerDependencies) -> None:
        self._deps = deps

    def delete(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        config_id: str,
        request: Any,
    ) -> dict[str, Any]:
        _enforce_supported_scope(jurisdiction, sector, self._deps.settings)
        auth_header = str(getattr(request, "headers", {}).get("authorization", "") or "")
        _enforce_auth_context(
            {},
            self._deps.settings,
            authorization_header=auth_header,
            require_token=True,
            required_scopes={"dataconv.config.write"},
            enforce_scopes_in_demo=True,
            expected_organization=tenant_id,
        )
        expected_id = str(config_id or "").strip()
        expected_tenant = str(tenant_id or "").strip().lower()
        expected_sector = str(sector or "").strip().lower()
        expected_country = str(jurisdiction or "").strip().upper()
        owned = next((
            config for config in self._deps.control_plane.list_configs()
            if config.object_id == expected_id
            and config.key.alternate_name == expected_tenant
            and config.key.sector == expected_sector
            and config.key.country.upper() == expected_country
        ), None)
        if owned is None:
            raise HTTPException(status_code=404, detail="Tenant adapter configuration not found")
        if not self._deps.control_plane.delete_config(owned.key):  # pragma: no cover - concurrent deletion
            raise HTTPException(status_code=404, detail="Tenant adapter configuration not found")
        return {"deleted": True, "id": owned.object_id}
