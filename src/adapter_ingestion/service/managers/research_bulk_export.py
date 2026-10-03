# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import re
import uuid
from typing import Any
from urllib.parse import urlsplit

from ...runtime import JobRequest, JobStatus
from ..api_support import HTTPException, _enforce_auth_context, _enforce_supported_scope, _extract_bearer_token
from ..auth_exchange import validate_session_access_token
from ..research import build_storage_namespace
from ..research_study import normalize_research_study_reference, sector_requires_professional_research_auth
from .dependencies import ApiManagerDependencies


_PATIENT_REFERENCE = re.compile(
    r"^Patient/(?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$",
    re.IGNORECASE,
)
_RESOURCE_TYPE = re.compile(r"^[A-Z][A-Za-z0-9]+$")
_SUPPORTED_EXPORT_TYPES = frozenset({
    "Patient", "ResearchSubject", "Composition", "DocumentReference", "Encounter",
    "AllergyIntolerance", "Condition", "DiagnosticReport", "Immunization",
    "MedicationStatement", "Observation", "Procedure",
})


def _absolute_url(request: Any, path: str) -> str:
    raw_url = str(getattr(request, "url", "") or "").strip()
    parsed = urlsplit(raw_url)
    return f"{parsed.scheme}://{parsed.netloc}{path}" if parsed.scheme and parsed.netloc else path


def _claims(resource: dict[str, Any]) -> dict[str, Any]:
    meta = resource.get("meta")
    return meta.get("claims", {}) if isinstance(meta, dict) and isinstance(meta.get("claims"), dict) else {}


def _coding(value: Any, display: Any = "") -> dict[str, Any]:
    raw = str(value or "").strip()
    text = str(display or "").strip()
    if not raw:
        return {"text": text} if text else {}
    system, separator, code = raw.partition("|")
    coding = {"code": code if separator else raw}
    if separator and system:
        coding["system"] = system
    if text:
        coding["display"] = text
    return {"coding": [coding], **({"text": text} if text else {})}


def _status(value: Any, default: str = "unknown") -> str:
    return str(value or default).strip().lower() or default


def _project_patient(subject: dict[str, Any], logical_id: str) -> dict[str, Any]:
    claims = _claims(subject)
    gender = str(claims.get("Subject.birthsex", claims.get("ResearchSubject.gender", "")) or "").strip().lower()
    gender = {
        "hembra": "female", "mujer": "female", "female": "female",
        "macho": "male", "hombre": "male", "male": "male",
    }.get(gender, "unknown")
    patient: dict[str, Any] = {"resourceType": "Patient", "id": logical_id, "active": True, "gender": gender}
    birthyear = str(claims.get("Subject.birthyear", claims.get("ResearchSubject.birthyear", "")) or "").strip()
    if re.fullmatch(r"\d{4}", birthyear):
        patient["birthDate"] = birthyear
    return patient


def _project_research_subject(subject: dict[str, Any], logical_id: str, study: str) -> dict[str, Any]:
    claims = _claims(subject)
    identifier = str(claims.get("ResearchSubject.identifier", "") or f"urn:uuid:{logical_id}").strip()
    return {
        "resourceType": "ResearchSubject", "id": logical_id,
        "identifier": [{"value": identifier}],
        "status": _status(claims.get("ResearchSubject.status"), "candidate"),
        "study": {"reference": study},
        "individual": {"reference": f"Patient/{logical_id}"},
    }


def _reference(value: Any, fallback: str = "") -> dict[str, Any]:
    raw = str(value or fallback).strip()
    return {"reference": raw} if raw else {}


def _identifier(value: Any) -> list[dict[str, Any]]:
    raw = str(value or "").strip()
    return [{"value": raw}] if raw else []


def _project_document_resource(
    resource: dict[str, Any], logical_id: str, resource_types_by_id: dict[str, str],
) -> dict[str, Any] | None:
    resource_type = str(resource.get("resourceType", "") or "").strip()
    claims = _claims(resource)
    rid = str(resource.get("id", "") or uuid.uuid4()).strip()
    patient = {"reference": f"Patient/{logical_id}"}
    if resource_type == "Composition":
        entry_references: list[dict[str, str]] = []
        for raw in str(claims.get("Composition.entry", "") or "").split(","):
            entry_id = raw.strip().removeprefix("urn:uuid:")
            target_type = resource_types_by_id.get(entry_id)
            if entry_id and target_type:
                entry_references.append({"reference": f"{target_type}/{entry_id}"})
        section: dict[str, Any] = {"entry": entry_references}
        section_code = _coding(claims.get("Composition.section"))
        if section_code:
            section["code"] = section_code
        return {
            "resourceType": "Composition", "id": rid, "status": "final",
            **({"identifier": {"value": str(claims["Composition.identifier"])}} if claims.get("Composition.identifier") else {}),
            "type": _coding(claims.get("Composition.type") or claims.get("Composition.section")),
            "subject": patient,
            **({"date": str(claims["Composition.date"])} if claims.get("Composition.date") else {}),
            "author": [_reference(claims.get("Composition.author")) or {"display": "Source organization"}],
            "title": str(claims.get("Composition.title") or "Clinical document"),
            "section": [section],
        }
    if resource_type == "DocumentReference":
        description = str(claims.get("DocumentReference.description") or "Clinical document").strip()
        projected: dict[str, Any] = {
            "resourceType": "DocumentReference", "id": rid,
            "status": _status(claims.get("DocumentReference.status"), "current"),
            "subject": patient,
            "description": description,
            "content": [{"attachment": {"title": description}}],
        }
        if claims.get("DocumentReference.docStatus"):
            projected["docStatus"] = _status(claims.get("DocumentReference.docStatus"), "preliminary")
        if claims.get("DocumentReference.identifier"):
            projected["identifier"] = _identifier(claims.get("DocumentReference.identifier"))
        if claims.get("DocumentReference.date"):
            projected["date"] = str(claims["DocumentReference.date"])
        if claims.get("DocumentReference.type"):
            projected["type"] = _coding(claims.get("DocumentReference.type"))
        if claims.get("DocumentReference.category"):
            projected["category"] = [_coding(claims.get("DocumentReference.category"))]
        return projected
    if resource_type == "Encounter":
        encounter_class = _coding(claims.get("Encounter.class"))
        coding = (encounter_class.get("coding") or [{}])[0]
        projected = {
            "resourceType": "Encounter", "id": rid,
            "status": _status(claims.get("Encounter.status"), "finished"),
            "class": coding,
            "subject": patient,
        }
        if claims.get("Encounter.identifier"):
            projected["identifier"] = _identifier(claims.get("Encounter.identifier"))
        if claims.get("Encounter.date"):
            value = str(claims["Encounter.date"])
            projected["period"] = {"start": value, "end": value}
        if claims.get("Encounter.servicetype"):
            projected["serviceType"] = _coding(claims.get("Encounter.servicetype"))
        return projected
    return None


def _project_clinical(
    resource: dict[str, Any], logical_id: str, resource_types_by_id: dict[str, str],
) -> dict[str, Any] | None:
    resource_type = str(resource.get("resourceType", "") or "").strip()
    if resource_type in {"Composition", "DocumentReference", "Encounter"}:
        return _project_document_resource(resource, logical_id, resource_types_by_id)
    if resource_type not in _SUPPORTED_EXPORT_TYPES - {"Patient", "ResearchSubject"}:
        return None
    claims = _claims(resource)
    rid = str(resource.get("id", "") or uuid.uuid4()).strip()
    projected: dict[str, Any] = {"resourceType": resource_type, "id": rid}
    subject_key = "patient" if resource_type in {"AllergyIntolerance", "Immunization"} else "subject"
    projected[subject_key] = {"reference": f"Patient/{logical_id}"}

    code_fields = {
        "AllergyIntolerance": ("code", "AllergyIntolerance.code", "AllergyIntolerance.code-text"),
        "Condition": ("code", "Condition.code", "Condition.code-text"),
        "DiagnosticReport": ("code", "DiagnosticReport.code", "DiagnosticReport.code-text"),
        "Immunization": ("vaccineCode", "Immunization.vaccine-code", "Immunization.vaccine-code-text"),
        "MedicationStatement": ("medicationCodeableConcept", "MedicationStatement.code", "MedicationStatement.code-text"),
        "Observation": ("code", "Observation.code", "Observation.code-text"),
        "Procedure": ("code", "Procedure.code", "Procedure.code-text"),
    }
    output_field, claim_field, text_field = code_fields[resource_type]
    code = _coding(claims.get(claim_field), claims.get(text_field))
    if code:
        projected[output_field] = code

    status_defaults = {
        "DiagnosticReport": "unknown", "Immunization": "completed", "MedicationStatement": "unknown",
        "Observation": "final", "Procedure": "unknown",
    }
    if resource_type in status_defaults:
        projected["status"] = _status(claims.get(f"{resource_type}.status"), status_defaults[resource_type])
    if resource_type == "Condition":
        projected["clinicalStatus"] = _coding(claims.get("Condition.clinical-status") or "http://terminology.hl7.org/CodeSystem/condition-clinical|active")
    if resource_type == "AllergyIntolerance":
        projected["clinicalStatus"] = _coding(claims.get("AllergyIntolerance.clinical-status") or "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical|active")

    date_fields = {
        "AllergyIntolerance": ("recordedDate", "AllergyIntolerance.date"),
        "Condition": ("onsetDateTime", "Condition.onset-datetime"),
        "DiagnosticReport": ("effectiveDateTime", "DiagnosticReport.date"),
        "Immunization": ("occurrenceDateTime", "Immunization.date"),
        "MedicationStatement": ("effectiveDateTime", "MedicationStatement.effective"),
        "Observation": ("effectiveDateTime", "Observation.date"),
        "Procedure": ("performedDateTime", "Procedure.date"),
    }
    output_date, claim_date = date_fields[resource_type]
    if str(claims.get(claim_date, "") or "").strip():
        projected[output_date] = str(claims[claim_date]).strip()
    if resource_type == "Observation" and str(claims.get("Observation.value-quantity", "") or "").strip():
        raw = str(claims["Observation.value-quantity"]).strip()
        number, _, unit = raw.partition("|")
        try:
            projected["valueQuantity"] = {"value": float(number), **({"unit": unit} if unit else {})}
        except ValueError:
            pass
    return projected


class ResearchBulkExportManager:
    """FHIR Bulk Data Group export over a bounded study-scoped pseudonymous cohort."""

    def __init__(self, deps: ApiManagerDependencies) -> None:
        self._deps = deps

    def _authorize(self, *, tenant_id: str, sector: str, study: str, request: Any) -> str:
        if bool(getattr(self._deps.settings, "demo_mode", True)):
            return "urn:demo:researcher"
        auth_header = str(getattr(request, "headers", {}).get("authorization", "") or "")
        bearer_token = _extract_bearer_token(auth_header)
        _enforce_auth_context(
            {"id_token": bearer_token} if bearer_token else {}, self._deps.settings,
            authorization_header=auth_header, require_token=True, required_scopes={"dataconv.read"},
            expected_organization=tenant_id, expected_research_study=study,
            require_study_research=sector_requires_professional_research_auth(sector, self._deps.settings),
        )
        claims = validate_session_access_token(bearer_token, self._deps.settings, force_secure=True)
        return str(claims.get("actor") or claims.get("sub") or "").strip()

    def _vault_id(self, tenant_id: str, jurisdiction: str, sector: str) -> str:
        _enforce_supported_scope(jurisdiction, sector, self._deps.settings)
        return build_storage_namespace(
            network_kind=self._deps.settings.network_mode, jurisdiction=jurisdiction,
            sector=sector, tenant_id=tenant_id,
        )

    def create_group(self, *, tenant_id: str, jurisdiction: str, sector: str, request: Any, body: dict[str, Any]) -> dict[str, Any]:
        if body.get("resourceType") != "Group" or body.get("type") not in {"person", "animal"} or body.get("actual") is not True:
            raise HTTPException(status_code=400, detail="an actual FHIR Group of type person or animal is required")
        identifiers = body.get("identifier")
        study_raw = identifiers[0].get("value") if isinstance(identifiers, list) and len(identifiers) == 1 and isinstance(identifiers[0], dict) else ""
        try:
            study = normalize_research_study_reference(str(study_raw or ""))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        self._authorize(tenant_id=tenant_id, sector=sector, study=study, request=request)
        members = body.get("member")
        if not isinstance(members, list) or not 1 <= len(members) <= 1000:
            raise HTTPException(status_code=400, detail="one to one thousand Patient members are required")
        vault_id = self._vault_id(tenant_id, jurisdiction, sector)
        references: list[str] = []
        for member in members:
            reference = str(((member.get("entity") or {}).get("reference", "")) if isinstance(member, dict) else "").strip()
            match = _PATIENT_REFERENCE.fullmatch(reference)
            if not match:
                raise HTTPException(status_code=400, detail="Group members must reference pseudonymous Patient/{uuid} resources")
            identifier = f"urn:uuid:{match.group('id').lower()}"
            found = self._deps.search_repo.search(
                vault_id=vault_id, resource_type="ResearchSubject", search_params={"study": study, "identifier": identifier},
            )
            if len(found) != 1:
                raise HTTPException(status_code=404 if not found else 409, detail=f"Patient member {reference} is not uniquely available in the authorized study")
            if reference not in references:
                references.append(reference)
        group_id = str(uuid.uuid4())
        stored = {
            "resourceType": "Group", "id": group_id,
            "meta": {"claims": {
                "@context": "org.hl7.fhir.api", "@type": "Group",
                "Group.identifier": study, "Group.type": body["type"], "Group.actual": "true",
                "Group.member": ",".join(references),
            }},
        }
        self._deps.vault_repo.put(vault_id, [stored], "Group")
        self._deps.search_repo.upsert(vault_id=vault_id, resource_type="Group", resource=stored)
        return {
            "resourceType": "Group", "id": group_id, "type": body["type"], "actual": True,
            "identifier": [{"value": study}], "member": [{"entity": {"reference": ref}} for ref in references],
        }

    def _load_group(self, vault_id: str, group_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        stored = self._deps.vault_repo.get(vault_id, group_id, "Group")
        if not stored:
            raise HTTPException(status_code=404, detail="Group not found")
        claims = _claims(stored)
        return stored, claims

    def kickoff(
        self, *, tenant_id: str, jurisdiction: str, sector: str, group_id: str, request: Any,
        output_format: str, resource_types: tuple[str, ...],
    ) -> dict[str, Any]:
        if output_format != "application/fhir+ndjson":
            raise HTTPException(status_code=400, detail="_outputFormat must be application/fhir+ndjson")
        if any(not _RESOURCE_TYPE.fullmatch(item) or item not in _SUPPORTED_EXPORT_TYPES for item in resource_types):
            raise HTTPException(status_code=400, detail="_type contains an unsupported resource type")
        vault_id = self._vault_id(tenant_id, jurisdiction, sector)
        _, group_claims = self._load_group(vault_id, group_id)
        study = normalize_research_study_reference(str(group_claims.get("Group.identifier", "")))
        actor = self._authorize(tenant_id=tenant_id, sector=sector, study=study, request=request)
        selected_types = set(resource_types or _SUPPORTED_EXPORT_TYPES)
        resources_by_type: dict[str, list[dict[str, Any]]] = {}
        for reference in str(group_claims.get("Group.member", "") or "").split(","):
            match = _PATIENT_REFERENCE.fullmatch(reference.strip())
            if not match:
                continue
            logical_id = match.group("id").lower()
            found = self._deps.search_repo.search(
                vault_id=vault_id, resource_type="ResearchSubject",
                search_params={"study": study, "identifier": f"urn:uuid:{logical_id}"},
            )
            if len(found) != 1:
                raise HTTPException(status_code=409, detail=f"Group member Patient/{logical_id} is no longer uniquely exportable")
            subject = found[0]
            if "Patient" in selected_types:
                resources_by_type.setdefault("Patient", []).append(_project_patient(subject, logical_id))
            if "ResearchSubject" in selected_types:
                resources_by_type.setdefault("ResearchSubject", []).append(_project_research_subject(subject, logical_id, study))
            contained_resources = [item for item in subject.get("contained", []) if isinstance(item, dict)]
            resource_types_by_id = {
                str(item.get("id", "")).strip(): str(item.get("resourceType", "")).strip()
                for item in contained_resources if str(item.get("id", "")).strip()
            }
            for contained in contained_resources:
                if not isinstance(contained, dict) or str(contained.get("resourceType", "")) not in selected_types:
                    continue
                projected = _project_clinical(contained, logical_id, resource_types_by_id)
                if projected:
                    resources_by_type.setdefault(projected["resourceType"], []).append(projected)
        request_path = f"/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/Group/{group_id}/$export"
        request_url = _absolute_url(request, request_path)
        input_ref = self._deps.blob_store.put_bytes(
            path=f"research-exports/requests/{uuid.uuid4()}.json",
            payload=json.dumps({"request": request_url, "groupId": group_id, "study": study, "resourcesByType": resources_by_type}, ensure_ascii=False).encode(),
            content_type="application/json",
        )
        job = self._deps.control_plane.submit_job(JobRequest(
            alternate_name=tenant_id, manufacturer="research-bulk-export", sector=sector, country=jurisdiction,
            input_ref=input_ref, requested_by=actor, mode="demo-ephemeral", research_study_reference=study,
        ))
        status_path = f"/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/bulk-status/{job.job_id}"
        return {
            "status": 202, "jobId": job.job_id,
            "contentLocation": _absolute_url(request, status_path),
        }

    def _authorized_job(self, *, tenant_id: str, sector: str, job_id: str, request: Any) -> Any:
        job = self._deps.control_plane.get_job(job_id)
        if not job or job.request.manufacturer != "research-bulk-export" or job.request.alternate_name != tenant_id or job.request.sector != sector:
            raise HTTPException(status_code=404, detail="Bulk Data export job not found")
        self._authorize(tenant_id=tenant_id, sector=sector, study=job.request.research_study_reference, request=request)
        return job

    def status(self, *, tenant_id: str, jurisdiction: str, sector: str, job_id: str, request: Any) -> dict[str, Any]:
        self._vault_id(tenant_id, jurisdiction, sector)
        job = self._authorized_job(tenant_id=tenant_id, sector=sector, job_id=job_id, request=request)
        if job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
            return {"status": 202, "headers": {"Retry-After": "2", "X-Progress": job.status}, "body": None}
        if job.status == JobStatus.FAILED:
            return {"status": 500, "headers": {}, "body": {"resourceType": "OperationOutcome", "issue": [{"severity": "error", "code": "processing", "diagnostics": job.error}]}}
        internal = json.loads(self._deps.blob_store.get_bytes(job.result_ref).decode())
        base = _absolute_url(
            request, f"/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/bulk-files/{job_id}",
        )
        manifest = {
            "transactionTime": internal["transactionTime"], "request": internal["request"],
            "requiresAccessToken": True,
            "output": [{"type": item["type"], "url": f"{base}/{item['type']}.ndjson", "count": item["count"]} for item in internal.get("output", [])],
            "error": internal.get("error", []),
        }
        return {"status": 200, "headers": {}, "body": manifest}

    def download(
        self, *, tenant_id: str, jurisdiction: str, sector: str, job_id: str,
        resource_type: str, request: Any,
    ) -> bytes:
        self._vault_id(tenant_id, jurisdiction, sector)
        job = self._authorized_job(tenant_id=tenant_id, sector=sector, job_id=job_id, request=request)
        if job.status != JobStatus.SUCCEEDED or resource_type not in _SUPPORTED_EXPORT_TYPES:
            raise HTTPException(status_code=404, detail="Bulk Data output file not found")
        manifest = json.loads(self._deps.blob_store.get_bytes(job.result_ref).decode())
        item = next((entry for entry in manifest.get("output", []) if entry.get("type") == resource_type), None)
        if not item:
            raise HTTPException(status_code=404, detail="Bulk Data output file not found")
        return self._deps.blob_store.get_bytes(str(item["ref"]))

    def cancel(self, *, tenant_id: str, jurisdiction: str, sector: str, job_id: str, request: Any) -> None:
        self._vault_id(tenant_id, jurisdiction, sector)
        self._authorized_job(tenant_id=tenant_id, sector=sector, job_id=job_id, request=request)
        self._deps.control_plane.delete_job(job_id)
