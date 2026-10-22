# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any

from ..api_support import HTTPException, _enforce_auth_context, _enforce_supported_scope, _extract_bearer_token
from ..auth_exchange import validate_session_access_token
from ..research import build_storage_namespace
from ..research_study import normalize_research_study_reference, sector_requires_professional_research_auth
from .dependencies import ApiManagerDependencies


class ResearchSubjectBundleManager:
    """Create or extend one study-bound pseudonymous twin from a direct document Bundle."""

    def __init__(self, deps: ApiManagerDependencies) -> None:
        self._deps = deps

    def handle_add_data(
        self, *, tenant_id: str, jurisdiction: str, sector: str, study: str,
        request: Any, body: dict[str, Any],
    ) -> dict[str, Any]:
        _enforce_supported_scope(jurisdiction, sector, self._deps.settings)
        try:
            study = normalize_research_study_reference(study)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        actor = self._authorize(request, tenant_id, study, sector)
        composition, resources, subject_id = _validate_document_bundle(body)
        identifier = f"urn:uuid:{subject_id}"
        vault_id = build_storage_namespace(
            network_kind=self._deps.settings.network_mode,
            jurisdiction=jurisdiction,
            sector=sector,
            tenant_id=tenant_id,
        )
        matches = self._deps.search_repo.search(
            vault_id=vault_id, resource_type="ResearchSubject", search_params={"identifier": identifier},
        )
        if len(matches) > 1:
            raise HTTPException(status_code=409, detail="ResearchSubject identifier is not unique")
        existing = matches[0] if matches else None
        existing_study = str((((existing or {}).get("meta") or {}).get("claims") or {}).get("ResearchSubject.study", "")).strip()
        if existing_study and existing_study != study:
            raise HTTPException(status_code=409, detail="ResearchSubject identifier belongs to another study")

        clinical = [_bind_clinical_resource(resource, identifier) for resource in resources]
        compositions = _section_compositions(
            composition=composition, resources=clinical, identifier=identifier,
            study=study, actor=actor, subject_id=subject_id,
        )
        subject = _merge_subject(existing, subject_id, identifier, study, [*compositions, *clinical])
        self._persist_with_compensation(vault_id, existing, subject, clinical)
        return {"created": existing is None, "researchSubject": subject}

    def _authorize(self, request: Any, tenant_id: str, study: str, sector: str) -> str:
        if bool(getattr(self._deps.settings, "demo_mode", True)):
            return "PractitionerRole/demo-research-professional"
        auth_header = str(getattr(request, "headers", {}).get("authorization", "") or "")
        token = _extract_bearer_token(auth_header)
        _enforce_auth_context(
            {"id_token": token} if token else {}, self._deps.settings,
            authorization_header=auth_header, require_token=True,
            required_scopes={"dataconv.review"}, expected_organization=tenant_id,
            expected_research_study=study,
            require_study_research=sector_requires_professional_research_auth(sector, self._deps.settings),
        )
        claims = validate_session_access_token(token, self._deps.settings, force_secure=True)
        return str(claims.get("actor") or claims.get("sub") or "").strip()

    def _persist_with_compensation(
        self, vault_id: str, existing: dict[str, Any] | None,
        subject: dict[str, Any], clinical: list[dict[str, Any]],
    ) -> None:
        subject_id = str(subject["id"])
        old_resources: dict[tuple[str, str], dict[str, Any]] = {}
        for resource in clinical:
            resource_type, resource_id = str(resource["resourceType"]), str(resource["id"])
            current = self._deps.search_repo.search(vault_id=vault_id, resource_type=resource_type, search_params={})
            matched = next((item for item in current if str(item.get("id", "")) == resource_id), None)
            if matched:
                old_resources[(resource_type, resource_id)] = matched
        try:
            if not self._deps.vault_repo.put(vault_id, [subject], "ResearchSubject"):
                raise RuntimeError("research_subject_vault_write_failed")
            if not self._deps.search_repo.upsert(vault_id=vault_id, resource_type="ResearchSubject", resource=subject):
                raise RuntimeError("research_subject_index_write_failed")
            for resource in clinical:
                if not self._deps.search_repo.upsert(
                    vault_id=vault_id, resource_type=str(resource["resourceType"]), resource=resource,
                ):
                    raise RuntimeError("research_subject_resource_index_write_failed")
        except Exception as exc:
            if existing:
                self._deps.vault_repo.put(vault_id, [existing], "ResearchSubject")
                self._deps.search_repo.upsert(vault_id=vault_id, resource_type="ResearchSubject", resource=existing)
            else:
                self._deps.vault_repo.delete(vault_id, subject_id, "ResearchSubject")
                self._deps.search_repo.delete(vault_id=vault_id, resource_type="ResearchSubject", resource_id=subject_id)
            for resource in clinical:
                key = (str(resource["resourceType"]), str(resource["id"]))
                if key in old_resources:
                    self._deps.search_repo.upsert(vault_id=vault_id, resource_type=key[0], resource=old_resources[key])
                else:
                    self._deps.search_repo.delete(vault_id=vault_id, resource_type=key[0], resource_id=key[1])
            raise HTTPException(status_code=503, detail="ResearchSubject Bundle could not be persisted atomically") from exc


def _validate_document_bundle(body: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    if body.get("resourceType") != "Bundle" or body.get("type") != "document":
        raise HTTPException(status_code=400, detail="Bundle.type=document is required")
    entries = body.get("entry")
    if not isinstance(entries, list) or not entries:
        raise HTTPException(status_code=400, detail="Bundle.entry is required")
    composition = (entries[0] or {}).get("resource") if isinstance(entries[0], dict) else None
    if not isinstance(composition, dict) or composition.get("resourceType") != "Composition":
        raise HTTPException(status_code=400, detail="Bundle.entry[0] must be Composition")
    subject_reference = str(((composition.get("subject") or {}).get("reference") or "")).strip()
    if subject_reference:
        prefix, separator, raw_id = subject_reference.partition("/")
        if not separator or prefix != "ResearchSubject" or not raw_id:
            raise HTTPException(status_code=400, detail="Composition.subject must reference ResearchSubject/<uuid>")
        subject_id = _canonical_uuid(raw_id)
    else:
        subject_id = str(uuid.uuid4())
    resources: list[dict[str, Any]] = []
    for entry in entries[1:]:
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(resource, dict):
            continue
        resource_type = str(resource.get("resourceType", "")).strip()
        if resource_type == "ResearchSubject":
            if resource.get("id") and _canonical_uuid(str(resource["id"])) != subject_id:
                raise HTTPException(status_code=409, detail="Bundle ResearchSubject does not match Composition.subject")
            continue
        if resource_type in {"Composition", "Patient"}:
            continue
        resource_id = str(resource.get("id", "")).strip()
        claims = ((resource.get("meta") or {}).get("claims") or {})
        if not resource_type or not resource_id or not isinstance(claims, dict):
            raise HTTPException(status_code=400, detail="Every clinical entry requires resourceType, id and meta.claims")
        resources.append(copy.deepcopy(resource))
    if not resources:
        raise HTTPException(status_code=400, detail="Bundle requires at least one clinical resource")
    return composition, resources, subject_id


def _canonical_uuid(value: str) -> str:
    try:
        parsed = uuid.UUID(str(value).removeprefix("urn:uuid:"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="ResearchSubject identifier must be a UUID") from exc
    return str(parsed)


def _bind_clinical_resource(resource: dict[str, Any], identifier: str) -> dict[str, Any]:
    bound = copy.deepcopy(resource)
    resource_type = str(bound["resourceType"])
    claims = dict(((bound.get("meta") or {}).get("claims") or {}))
    claims["@context"] = "org.hl7.fhir.api"
    claims[f"{resource_type}.identifier"] = str(bound["id"])
    claims[f"{resource_type}.subject"] = identifier
    bound["meta"] = {**(bound.get("meta") or {}), "claims": claims}
    return bound


def _section_compositions(
    *, composition: dict[str, Any], resources: list[dict[str, Any]], identifier: str,
    study: str, actor: str, subject_id: str,
) -> list[dict[str, Any]]:
    by_reference = {f'{resource["resourceType"]}/{resource["id"]}': resource for resource in resources}
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    result: list[dict[str, Any]] = []
    for index, section in enumerate(composition.get("section") or []):
        coding = (((section or {}).get("code") or {}).get("coding") or [{}])[0]
        system, code = str(coding.get("system", "")).strip(), str(coding.get("code", "")).strip()
        token = f"{system}|{code}" if system else code
        references = [
            str((item or {}).get("reference", "")).strip()
            for item in (section or {}).get("entry") or []
            if str((item or {}).get("reference", "")).strip() in by_reference
        ]
        if not token or not references:
            continue
        composition_id = f"research-data-{subject_id}-{index + 1}"
        result.append({
            "resourceType": "Composition", "id": composition_id,
            "meta": {"claims": {
                "@context": "org.hl7.fhir.api",
                "Composition.identifier": f"urn:uuid:{composition_id}",
                "Composition.subject": identifier,
                "Composition.author": actor,
                "Composition.attester": actor,
                "Composition.attester-mode": "professional",
                "Composition.attester-time": now,
                "Composition.date": now,
                "Composition.research-study": study,
                "Composition.section": token,
                "Composition.entry": ",".join(f"urn:uuid:{by_reference[reference]['id']}" for reference in references),
            }},
        })
    if not result:
        raise HTTPException(status_code=400, detail="Composition requires at least one coded section with entries")
    return result


def _merge_subject(
    existing: dict[str, Any] | None, subject_id: str, identifier: str,
    study: str, additions: list[dict[str, Any]],
) -> dict[str, Any]:
    subject = copy.deepcopy(existing) if existing else {
        "resourceType": "ResearchSubject", "id": subject_id, "contained": [], "meta": {"claims": {}},
    }
    claims = dict(((subject.get("meta") or {}).get("claims") or {}))
    claims.update({
        "@context": "org.hl7.fhir.api",
        "ResearchSubject.identifier": identifier,
        "ResearchSubject.study": study,
        "ResearchSubject.status": claims.get("ResearchSubject.status") or "candidate",
    })
    subject["meta"] = {**(subject.get("meta") or {}), "claims": claims}
    keyed = {
        (str(resource.get("resourceType", "")), str(resource.get("id", ""))): resource
        for resource in subject.get("contained") or [] if isinstance(resource, dict)
    }
    for resource in additions:
        keyed[(str(resource["resourceType"]), str(resource["id"]))] = resource
    subject["contained"] = list(keyed.values())
    return subject
