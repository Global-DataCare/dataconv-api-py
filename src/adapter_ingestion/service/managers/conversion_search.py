# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from ..api_support import HTTPException, _enforce_auth_context, _extract_bearer_token
from ..observability import log_event
from .dependencies import ApiManagerDependencies
from ..research import build_vault_id


class ConversionSearchManager:
    def __init__(self, deps: ApiManagerDependencies) -> None:
        self._deps = deps

    def handle(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        resource_type: str,
        response: Any,
        request: Any,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        # Handle Authentication
        auth_mode = str(self._deps.settings.auth_mode or "parse-only").lower().strip()
        auth_header = ""
        try:
            auth_header = str(request.headers.get("authorization", "") or "")
        except Exception:
            pass

        if auth_mode != "parse-only":
            bearer_token = _extract_bearer_token(auth_header)
            dummy_payload = {"id_token": bearer_token} if bearer_token else {}
            _enforce_auth_context(
                dummy_payload, 
                self._deps.settings, 
                authorization_header=auth_header, 
                require_token=True
            )

        # Combine query parameters and JSON body for search arguments
        search_params = {}
        for k, v in request.query_params.items():
            normalized_key = str(k or "").strip().lower()
            if normalized_key:
                search_params[normalized_key] = v
        
        if isinstance(body, dict):
            for k, v in body.items():
                normalized_key = str(k or "").strip().lower()
                if normalized_key:
                    search_params[normalized_key] = v

        vault_id = build_vault_id(sector=sector, tenant_id=tenant_id)

        filtered_results = self._deps.search_repo.search(
            vault_id=vault_id,
            resource_type=resource_type,
            search_params=search_params,
        )

        log_event(
            "research_search_executed",
            source="search-endpoint",
            vaultId=vault_id,
            resourceType=resource_type,
            matchedCount=len(filtered_results),
        )

        return {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": len(filtered_results),
            "entry": [
                {
                    "fullUrl": f"urn:uuid:{resource.get('id', '')}",
                    "resource": resource
                }
                for resource in filtered_results
            ]
        }
