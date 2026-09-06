# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from ..api_support import HTTPException, _enforce_auth_context, _enforce_supported_scope, _extract_bearer_token
from ..observability import log_event
from .dependencies import ApiManagerDependencies
from ..research import build_storage_namespace
from ..research_study import normalize_research_study_reference


FHIR_R4_FINANCIAL_SEARCH_PARAMETERS: dict[str, frozenset[str]] = {
    "Invoice": frozenset({"date", "identifier", "issuer", "recipient", "status", "subject"}),
    "ChargeItem": frozenset({"code", "identifier", "occurrence", "subject"}),
}


def _validate_financial_search_parameters(
    resource_type: str,
    search_params: dict[str, Any],
) -> None:
    supported = FHIR_R4_FINANCIAL_SEARCH_PARAMETERS.get(str(resource_type or "").strip())
    if supported is None:
        return
    unsupported = sorted(set(search_params) - supported)
    if unsupported:
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{unsupported[0]}' is not a supported FHIR R4 search parameter "
                f"for {resource_type}; supported: {', '.join(sorted(supported))}"
            ),
        )


def _search_params_from_fhir_parameters(body: dict[str, Any]) -> dict[str, Any]:
    if str(body.get("resourceType", "") or "").strip() != "Parameters":
        return {
            str(key or "").strip().lower(): value
            for key, value in body.items()
            if str(key or "").strip() and not str(key or "").strip().startswith("_")
        }

    raw_parameters = body.get("parameter", [])
    if not isinstance(raw_parameters, list):
        raise HTTPException(status_code=400, detail="FHIR Parameters.parameter must be an array")

    search_params: dict[str, Any] = {}
    for parameter in raw_parameters:
        if not isinstance(parameter, dict):
            continue
        name = str(parameter.get("name", "") or "").strip().lower()
        if not name or name.startswith("_"):
            continue
        value_keys = [key for key in parameter if str(key).startswith("value")]
        if len(value_keys) != 1:
            raise HTTPException(
                status_code=400,
                detail=f"FHIR search parameter '{name}' must contain exactly one value[x]",
            )
        value = parameter[value_keys[0]]
        existing = search_params.get(name)
        if existing is None:
            search_params[name] = value
        elif isinstance(existing, list):
            existing.append(value)
        else:
            search_params[name] = [existing, value]
    return search_params


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
        _enforce_supported_scope(jurisdiction, sector, self._deps.settings)
        # Handle Authentication
        demo_mode = bool(getattr(self._deps.settings, "demo_mode", True))
        auth_header = ""
        try:
            auth_header = str(request.headers.get("authorization", "") or "")
        except Exception:
            pass

        if not demo_mode:
            bearer_token = _extract_bearer_token(auth_header)
            dummy_payload = {"id_token": bearer_token} if bearer_token else {}
            _enforce_auth_context(
                dummy_payload, 
                self._deps.settings, 
                authorization_header=auth_header, 
                require_token=True,
                required_scopes={"dataconv.read"},
                expected_organization=tenant_id,
            )

        # Combine query parameters and JSON body for search arguments.
        # Ignore control/meta params (FHIR-style underscore keys like _count, _sort, etc.)
        # because repository filtering expects business claim fields.
        search_params = {}
        query_params = request.query_params
        items = query_params.multi_items() if hasattr(query_params, "multi_items") else query_params.items()
        for k, v in items:
            normalized_key = str(k or "").strip().lower()
            if normalized_key and not normalized_key.startswith("_"):
                existing = search_params.get(normalized_key)
                if existing is None:
                    search_params[normalized_key] = v
                elif isinstance(existing, list):
                    existing.append(v)
                else:
                    search_params[normalized_key] = [existing, v]
        
        if isinstance(body, dict):
            search_params.update(_search_params_from_fhir_parameters(body))

        _validate_financial_search_parameters(resource_type, search_params)
        if str(resource_type or "").strip() == "ResearchSubject":
            raw_study = search_params.get("study")
            if isinstance(raw_study, list):
                if len(raw_study) != 1:
                    raise HTTPException(status_code=400, detail="ResearchSubject study must contain one reference")
                raw_study = raw_study[0]
            if isinstance(raw_study, dict):
                raw_study = raw_study.get("reference")
            if not str(raw_study or "").strip():
                raise HTTPException(status_code=400, detail="ResearchSubject study search parameter is required")
            try:
                search_params["study"] = normalize_research_study_reference(raw_study)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        vault_id = build_storage_namespace(
            network_kind=self._deps.settings.network_mode,
            jurisdiction=jurisdiction,
            sector=sector,
            tenant_id=tenant_id,
        )

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
