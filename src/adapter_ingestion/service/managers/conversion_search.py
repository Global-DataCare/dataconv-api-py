# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any
import re
import uuid
from datetime import datetime, timezone

from ..api_support import HTTPException, _enforce_auth_context, _enforce_supported_scope, _extract_bearer_token
from ..observability import log_event
from .dependencies import ApiManagerDependencies
from ..research import build_storage_namespace
from ..research_study import normalize_research_study_reference, sector_requires_professional_research_auth
from ..auth_exchange import validate_session_access_token


FHIR_R4_FINANCIAL_SEARCH_PARAMETERS: dict[str, frozenset[str]] = {
    "Invoice": frozenset({"date", "identifier", "issuer", "recipient", "status", "subject"}),
    "ChargeItem": frozenset({"code", "identifier", "occurrence", "subject"}),
}

RESEARCH_SEARCH_PARAMETER_CATALOG: dict[str, frozenset[str]] = {
    "ResearchSubject": frozenset({"birthyear", "identifier", "status", "study"}),
    "AllergyIntolerance": frozenset({"code:text", "code", "date"}),
    "Condition": frozenset({"code:text", "code", "onset-date"}),
    "DiagnosticReport": frozenset({"code:text", "code", "date"}),
    "Immunization": frozenset({"vaccine-code:text", "vaccine-code", "date"}),
    "MedicationStatement": frozenset({"code:text", "code", "effective"}),
    "Observation": frozenset({"code:text", "code", "date", "value-quantity"}),
    "Procedure": frozenset({"code:text", "code", "date"}),
}

_QUALIFIED_SEARCH_PARAMETER = re.compile(r"^(?P<resource>[A-Z][A-Za-z0-9]*)\.(?P<parameter>[a-z][a-z0-9:-]*)$")


def _validate_research_search_parameter(name: str) -> tuple[str, str]:
    match = _QUALIFIED_SEARCH_PARAMETER.fullmatch(name)
    if not match:
        raise HTTPException(status_code=400, detail=f"'{name}' is not a supported research search parameter")
    resource = match.group("resource")
    parameter = match.group("parameter")
    if parameter not in RESEARCH_SEARCH_PARAMETER_CATALOG.get(resource, frozenset()):
        raise HTTPException(status_code=400, detail=f"'{name}' is not a supported research search parameter")
    return resource, parameter


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
        raw_name = str(parameter.get("name", "") or "").strip()
        name = raw_name if "." in raw_name else raw_name.lower()
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


def _require_resource_qualified_research_parameters(body: dict[str, Any]) -> None:
    """Reject ambiguous cohort criteria before stripping their resource family.

    ``Condition.code:text`` on the wire maps to canonical claim
    ``Condition.code-text`` and then to private key ``condition_code-text``.
    """
    if str(body.get("resourceType", "") or "").strip() != "Parameters":
        return
    for parameter in body.get("parameter", []):
        if not isinstance(parameter, dict):
            continue
        name = str(parameter.get("name", "") or "").strip()
        if name and not name.startswith("_") and "." not in name:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"FHIR research Parameters.parameter.name '{name}' must be resource-qualified "
                    "as ResourceType.search-parameter"
                ),
            )


def _qualified_research_search(
    search_repo: Any,
    *,
    vault_id: str,
    search_params: dict[str, Any],
    study: str,
) -> list[dict[str, Any]]:
    """Resolve resource-qualified criteria to their intersected ResearchSubjects."""
    subject_params: dict[str, Any] = {"study": study}
    resource_params: dict[str, dict[str, Any]] = {}
    for raw_name, value in search_params.items():
        name = str(raw_name or "").strip()
        if name in {"study", "ResearchSubject.study"}:
            continue
        resource, parameter = _validate_research_search_parameter(name)
        if resource == "ResearchSubject":
            subject_params[parameter] = value
        else:
            resource_params.setdefault(resource, {})[parameter] = value

    subjects = search_repo.search(
        vault_id=vault_id,
        resource_type="ResearchSubject",
        search_params=subject_params,
    )
    subject_by_identifier = {
        str(((resource.get("meta") or {}).get("claims") or {}).get("ResearchSubject.identifier", "")).strip(): resource
        for resource in subjects
    }
    subject_by_identifier.pop("", None)
    candidates = set(subject_by_identifier)
    for resource_type, params in resource_params.items():
        matches = search_repo.search(
            vault_id=vault_id,
            resource_type=resource_type,
            search_params=params,
        )
        matching_subjects = {
            str(((resource.get("meta") or {}).get("claims") or {}).get(f"{resource_type}.subject", "")).strip()
            for resource in matches
        }
        candidates.intersection_update(matching_subjects)
        if not candidates:
            break
    return [subject_by_identifier[identifier] for identifier in subject_by_identifier if identifier in candidates]


def _parameter_reference(value: Any) -> str:
    if isinstance(value, list):
        if len(value) != 1:
            raise HTTPException(status_code=400, detail="ResearchSubject parameter must contain one value")
        value = value[0]
    if isinstance(value, dict):
        value = value.get("reference")
    return str(value or "").strip()


def _materialize_research_subject_summary(subject: dict[str, Any]) -> dict[str, Any]:
    contained = [item for item in subject.get("contained", []) if isinstance(item, dict)]
    clinical = [item for item in contained if str(item.get("resourceType", "")) != "Composition"]
    by_id = {str(item.get("id", "")).strip(): item for item in clinical if str(item.get("id", "")).strip()}
    sections: list[dict[str, Any]] = []
    for composition in contained:
        if str(composition.get("resourceType", "")) != "Composition":
            continue
        claims = ((composition.get("meta") or {}).get("claims") or {})
        raw_code = str(claims.get("Composition.section", "") or "").strip()
        system, separator, code = raw_code.partition("|")
        references: list[dict[str, str]] = []
        for raw_reference in str(claims.get("Composition.entry", "") or "").split(","):
            identifier = raw_reference.strip().split(":")[-1]
            resource = by_id.get(identifier)
            if not resource:
                continue
            references.append({"reference": f'{resource.get("resourceType")}/{identifier}'})
        sections.append({
            "title": code if separator else raw_code,
            "code": {"coding": [{
                **({"system": system} if separator and system else {}),
                "code": code if separator else raw_code,
            }]},
            "entry": references,
        })

    identifier = str(((subject.get("meta") or {}).get("claims") or {}).get("ResearchSubject.identifier", "")).strip()
    logical_id = str(subject.get("id", "") or identifier.removeprefix("urn:uuid:")).strip()
    summary_composition = {
        "resourceType": "Composition",
        "id": f"research-summary-{logical_id}",
        "status": "final",
        "subject": {"reference": identifier or f"ResearchSubject/{logical_id}"},
        "section": sections,
    }
    projected_subject = {key: value for key, value in subject.items() if key not in {"contained", "composition"}}
    resources = [summary_composition, projected_subject, *clinical]
    return {
        "resourceType": "Bundle",
        "type": "document",
        "identifier": {"value": f"research-summary-{logical_id}"},
        "entry": [{
            "fullUrl": f'urn:uuid:{resource.get("id", "")}',
            "resource": resource,
        } for resource in resources],
    }


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

        if not demo_mode and str(resource_type or "").strip() != "ResearchSubject":
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
            if str(resource_type or "").strip() == "ResearchSubject":
                _require_resource_qualified_research_parameters(body)
            search_params.update(_search_params_from_fhir_parameters(body))

        _validate_financial_search_parameters(resource_type, search_params)
        if str(resource_type or "").strip() == "ResearchSubject":
            raw_study = search_params.get("ResearchSubject.study", search_params.get("study"))
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
                if "ResearchSubject.study" in search_params:
                    search_params["ResearchSubject.study"] = search_params["study"]
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
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
                    expected_research_study=str(search_params["study"]),
                    require_study_research=sector_requires_professional_research_auth(sector, self._deps.settings),
                )

        vault_id = build_storage_namespace(
            network_kind=self._deps.settings.network_mode,
            jurisdiction=jurisdiction,
            sector=sector,
            tenant_id=tenant_id,
        )

        uses_qualified_research_search = (
            str(resource_type or "").strip() == "ResearchSubject"
            and any("." in str(name or "") for name in search_params)
        )
        filtered_results = _qualified_research_search(
            self._deps.search_repo,
            vault_id=vault_id,
            search_params=search_params,
            study=str(search_params.get("study", "")),
        ) if uses_qualified_research_search else self._deps.search_repo.search(
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

    def handle_summary(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Any,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        _enforce_supported_scope(jurisdiction, sector, self._deps.settings)
        parameters = _search_params_from_fhir_parameters(body)
        study = _parameter_reference(parameters.get("ResearchSubject.study", parameters.get("study")))
        identifier = _parameter_reference(parameters.get("ResearchSubject.identifier", parameters.get("identifier")))
        if not study:
            raise HTTPException(status_code=400, detail="ResearchSubject study search parameter is required")
        if not identifier:
            raise HTTPException(status_code=400, detail="ResearchSubject identifier is required")
        try:
            study = normalize_research_study_reference(study)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        demo_mode = bool(getattr(self._deps.settings, "demo_mode", True))
        if not demo_mode:
            auth_header = str(getattr(request, "headers", {}).get("authorization", "") or "")
            bearer_token = _extract_bearer_token(auth_header)
            _enforce_auth_context(
                {"id_token": bearer_token} if bearer_token else {},
                self._deps.settings,
                authorization_header=auth_header,
                require_token=True,
                required_scopes={"dataconv.read"},
                expected_organization=tenant_id,
                expected_research_study=study,
                require_study_research=sector_requires_professional_research_auth(sector, self._deps.settings),
            )

        vault_id = build_storage_namespace(
            network_kind=self._deps.settings.network_mode,
            jurisdiction=jurisdiction,
            sector=sector,
            tenant_id=tenant_id,
        )
        matches = self._deps.search_repo.search(
            vault_id=vault_id,
            resource_type="ResearchSubject",
            search_params={"study": study, "identifier": identifier},
        )
        if not matches:
            raise HTTPException(status_code=404, detail="ResearchSubject not found in the authorized study")
        if len(matches) != 1:
            raise HTTPException(status_code=409, detail="ResearchSubject identifier is not unique in the authorized study")
        return _materialize_research_subject_summary(matches[0])

    def handle_tag(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Any,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist a researcher-owned workset marker without changing the canonical twin."""
        _enforce_supported_scope(jurisdiction, sector, self._deps.settings)
        parameters = _search_params_from_fhir_parameters(body)
        study = _parameter_reference(parameters.get("ResearchSubject.study", parameters.get("study")))
        identifier = _parameter_reference(parameters.get("ResearchSubject.identifier", parameters.get("identifier")))
        tag = parameters.get("tag")
        if not isinstance(tag, dict):
            raise HTTPException(status_code=400, detail="tag valueCoding is required")
        system = str(tag.get("system", "") or "").strip()
        code = str(tag.get("code", "") or "").strip()
        if not re.fullmatch(r"urn:multibase:z[A-Za-z0-9]+", system):
            raise HTTPException(status_code=400, detail="tag system must be a stable actor URN")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", code):
            raise HTTPException(status_code=400, detail="tag code must be machine-safe")
        try:
            study = normalize_research_study_reference(study)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not identifier.startswith("urn:uuid:"):
            raise HTTPException(status_code=400, detail="ResearchSubject identifier must be a UUID URN")

        auth_header = str(getattr(request, "headers", {}).get("authorization", "") or "")
        bearer_token = _extract_bearer_token(auth_header)
        demo_mode = bool(getattr(self._deps.settings, "demo_mode", True))
        actor = "urn:demo:researcher"
        if not demo_mode:
            _enforce_auth_context(
                {"id_token": bearer_token} if bearer_token else {}, self._deps.settings,
                authorization_header=auth_header, require_token=True,
                required_scopes={"dataconv.review"}, expected_organization=tenant_id,
                expected_research_study=study,
                require_study_research=sector_requires_professional_research_auth(sector, self._deps.settings),
            )
            session_claims = validate_session_access_token(bearer_token, self._deps.settings, force_secure=True)
            actor = str(session_claims.get("actor") or session_claims.get("sub") or "").strip()

        vault_id = build_storage_namespace(
            network_kind=self._deps.settings.network_mode, jurisdiction=jurisdiction,
            sector=sector, tenant_id=tenant_id,
        )
        matches = self._deps.search_repo.search(
            vault_id=vault_id, resource_type="ResearchSubject",
            search_params={"study": study, "identifier": identifier},
        )
        if len(matches) != 1:
            raise HTTPException(status_code=404 if not matches else 409, detail="ResearchSubject is not uniquely available in the authorized study")
        tag_token = f"{system}|{code}"
        existing = self._deps.vault_repo.query(vault_id, {
            "Composition.subject": identifier,
            "Composition.author": actor,
            "Composition.research-study": study,
            "Composition.meta-tag": tag_token,
        }, "Composition")
        selected = parameters.get("selected", True)
        if selected is False:
            for marker in existing:
                marker_id = str(marker.get("id", "") or "").strip()
                if marker_id:
                    self._deps.vault_repo.delete(vault_id, marker_id, "Composition")
                    self._deps.search_repo.delete(vault_id=vault_id, resource_type="Composition", resource_id=marker_id)
            return {"removed": bool(existing), "tag": code}
        if existing:
            return existing[0]
        selection_id = str(uuid.uuid4())
        selection = {
            "resourceType": "Composition", "id": selection_id,
            "meta": {"claims": {
                "@context": "org.hl7.fhir.api",
                "@type": "Composition:ResearcherWorkingSelection",
                "Composition.identifier": f"urn:uuid:{selection_id}",
                "Composition.subject": identifier,
                "Composition.author": actor,
                "Composition.date": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "Composition.research-study": study,
                "Composition.meta-tag": tag_token,
                "Composition.userSelected": "true",
            }},
        }
        self._deps.vault_repo.put(vault_id, [selection], "Composition")
        self._deps.search_repo.upsert(vault_id=vault_id, resource_type="Composition", resource=selection)
        return selection
