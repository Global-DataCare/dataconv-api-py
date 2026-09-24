# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from ..api_support import (
    HTTPException,
    _compose_software_id_token,
    _enforce_auth_context,
    _enforce_supported_scope,
)
from .dependencies import ApiManagerDependencies


def _public_content(payload: dict[str, Any]) -> dict[str, Any]:
    content = dict(payload or {})
    schema_config = content.pop("schemaConfig", None)
    if isinstance(schema_config, dict) and not isinstance(content.get("mappingConfig"), dict):
        content["mappingConfig"] = dict(schema_config)
    return content


def _bounded_integer(value: Any, *, default: int, minimum: int, maximum: int, name: str) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{name} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise HTTPException(status_code=400, detail=f"{name} must be between {minimum} and {maximum}")
    return parsed


class TenantConfigSearchManager:
    """List tenant configurations available to an authorized study importer."""

    def __init__(self, deps: ApiManagerDependencies) -> None:
        self._deps = deps

    def search(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Any,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        _enforce_supported_scope(jurisdiction, sector, self._deps.settings)
        auth_header = str(getattr(request, "headers", {}).get("authorization", "") or "")
        _enforce_auth_context(
            {},
            self._deps.settings,
            authorization_header=auth_header,
            require_token=True,
            required_scopes={"dataconv.config.read"},
            enforce_scopes_in_demo=True,
            expected_organization=tenant_id,
        )
        query = body if isinstance(body, dict) else {}
        count = _bounded_integer(query.get("_count"), default=20, minimum=1, maximum=100, name="_count")
        offset = _bounded_integer(query.get("_offset"), default=0, minimum=0, maximum=1_000_000, name="_offset")
        requested_software = str(query.get("softwareId") or "").strip().lower()
        expected_tenant = str(tenant_id or "").strip().lower()
        expected_sector = str(sector or "").strip().lower()
        expected_country = str(jurisdiction or "").strip().upper()

        configs = [
            config for config in self._deps.control_plane.list_configs()
            if config.key.alternate_name == expected_tenant
            and config.key.sector == expected_sector
            and config.key.country.upper() == expected_country
            and (
                not requested_software
                or config.key.manufacturer == requested_software
                or _compose_software_id_token(
                    config.key.manufacturer,
                    config.key.manufacturer_version,
                ).lower() == requested_software
            )
        ]
        configs.sort(key=lambda config: (
            config.key.manufacturer,
            config.key.manufacturer_version,
            config.updated_at,
        ))
        page = configs[offset : offset + count]
        return {
            "total": len(configs),
            "data": [
                {
                    "id": config.object_id,
                    "type": config.object_type,
                    "tenantId": config.key.alternate_name,
                    "sector": config.key.sector,
                    "softwareId": _compose_software_id_token(
                        config.key.manufacturer,
                        config.key.manufacturer_version,
                    ),
                    "softwareVersion": config.key.manufacturer_version,
                    "country": config.key.country,
                    "facilityId": config.key.facility_id,
                    "revision": str(config.revision),
                    "createdAt": config.created_at,
                    "updatedAt": config.updated_at,
                    "audit": dict(config.audit or {}),
                    "content": _public_content(config.content),
                }
                for config in page
            ],
        }
