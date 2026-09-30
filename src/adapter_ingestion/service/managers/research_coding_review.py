# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import re
from typing import Any

from ...ai.terminology import TerminologyCandidate, TerminologySearchRequest
from gdc_data_utils import (
    ConditionClaim,
    DiagnosticReportClaim,
    DocumentReferenceClaim,
    FHIR_API_CONTEXT,
    ImmunizationClaim,
    ProcedureClaim,
)
from ...models import stable_uuid
from ...source_concept_classification import classify_source_concept
from ..api_support import HTTPException, _enforce_auth_context, _enforce_supported_scope
from ..coding_review import apply_coding_reviews, has_pending_coding_proposals
from ..research import build_storage_namespace
from ..research_drafts import _safe_token
from ..research_study import (
    RESEARCH_SUBJECT_STUDY_CLAIM,
    normalize_research_study_reference,
    sector_requires_professional_research_auth,
)
from .conversion_job_search import _integer_parameter, _parameter_values
from .dependencies import ApiManagerDependencies


def _study_from_reference(value: Any) -> str:
    raw = value.get("reference") if isinstance(value, dict) else value
    try:
        return normalize_research_study_reference(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _resources(subject: dict[str, Any]) -> list[dict[str, Any]]:
    result = [subject]
    contained = subject.get("contained")
    if isinstance(contained, list):
        for item in contained:
            if isinstance(item, dict):
                result.extend(_resources(item))
    return result


def _has_pending(subject: dict[str, Any]) -> bool:
    return any(has_pending_coding_proposals(resource) for resource in _resources(subject))


def _candidate(resource_type: str, field: str, value: TerminologyCandidate) -> dict[str, Any]:
    return {
        "id": sha256("|".join((
            resource_type,
            field,
            value.system,
            value.code,
        )).encode("utf-8")).hexdigest()[:24],
        "system": value.system,
        "code": value.code,
        "display": value.display,
        "source": value.source,
        "recommendationPercent": 0.0,
        "evidence": "terminology candidate",
    }


_RECLASSIFICATION_TARGETS = {
    ("Condition", ConditionClaim.CODE): {
        "identifier": ConditionClaim.IDENTIFIER,
        "subject": ConditionClaim.SUBJECT,
        "status": {
            ConditionClaim.CLINICAL_STATUS: "active",
            ConditionClaim.VERIFICATION_STATUS: "provisional",
        },
    },
    ("Procedure", ProcedureClaim.CODE): {
        "identifier": ProcedureClaim.IDENTIFIER,
        "subject": ProcedureClaim.SUBJECT,
        "status": {ProcedureClaim.STATUS: "unknown"},
    },
    ("DiagnosticReport", DiagnosticReportClaim.CODE): {
        "identifier": DiagnosticReportClaim.IDENTIFIER,
        "subject": DiagnosticReportClaim.SUBJECT,
        "status": {DiagnosticReportClaim.STATUS: "unknown"},
    },
}


def _reference_ids(value: Any) -> list[str]:
    return [
        token.strip().removeprefix("urn:uuid:").rsplit("/", 1)[-1]
        for token in str(value or "").split(",")
        if token.strip()
    ]


def _resource_claims(resource: dict[str, Any]) -> dict[str, Any]:
    meta = resource.get("meta")
    claims = meta.get("claims") if isinstance(meta, dict) else None
    return claims if isinstance(claims, dict) else {}


def _pending_proposals(resource: dict[str, Any]) -> list[dict[str, Any]]:
    meta = resource.get("meta")
    proposals = meta.get("codingProposals") if isinstance(meta, dict) else None
    return [
        proposal for proposal in proposals or []
        if isinstance(proposal, dict) and str(proposal.get("status", "")).strip() == "proposed"
    ]


def _backfill_immunizations_from_imported_documents(
    subject: dict[str, Any],
    *,
    vault_id: str,
    default_language: str,
) -> None:
    """Recover reviewable administrations from older drafts without re-uploading the workbook."""

    contained = subject.get("contained")
    if not isinstance(contained, list):
        return
    subject_id = str(subject.get("id", "") or "").strip()
    existing_ids = {
        str(resource.get("id", "") or "").strip()
        for resource in contained
        if isinstance(resource, dict)
    }
    additions: list[dict[str, Any]] = []
    for document in contained:
        if not isinstance(document, dict) or str(document.get("resourceType", "")) != "DocumentReference":
            continue
        document_id = str(document.get("id", "") or "").strip()
        claims = _resource_claims(document)
        source_text = str(claims.get(DocumentReferenceClaim.DESCRIPTION, "") or "").strip()
        classified = classify_source_concept(
            section="",
            family="",
            subfamily="",
            concept=source_text,
            subject_kind="animal",
        )
        if [candidate.resource_type for candidate in classified] != ["Immunization"]:
            continue
        resource_id = stable_uuid(
            vault_id,
            subject_id,
            "document-immunization-backfill",
            document_id,
            source_text,
        )
        if resource_id in existing_ids:
            continue
        language = str(claims.get(DocumentReferenceClaim.LANGUAGE, "") or default_language).strip() or "und"
        immunization_claims = {
            "@context": FHIR_API_CONTEXT,
            ImmunizationClaim.IDENTIFIER: resource_id,
            ImmunizationClaim.SUBJECT: f"ResearchSubject/{subject_id}",
            ImmunizationClaim.STATUS: "completed",
            ImmunizationClaim.DATE: str(claims.get(DocumentReferenceClaim.DATE, "") or "").strip(),
            ImmunizationClaim.VACCINE_CODE_TEXT: source_text,
            "Immunization.language": language,
        }
        additions.append({
            "resourceType": "Immunization",
            "id": resource_id,
            "meta": {"claims": immunization_claims},
        })
        existing_ids.add(resource_id)
        for composition in contained:
            if not isinstance(composition, dict) or str(composition.get("resourceType", "")) != "Composition":
                continue
            composition_claims = _resource_claims(composition)
            entry_ids = _reference_ids(composition_claims.get("Composition.entry"))
            if document_id not in entry_ids:
                continue
            entry_ids.append(resource_id)
            composition_claims["Composition.entry"] = ",".join(
                f"urn:uuid:{entry_id}" for entry_id in dict.fromkeys(entry_ids)
            )
    contained.extend(additions)


def _hydrate_subject(
    vault_repo: Any,
    vault_id: str,
    stored_subject: dict[str, Any],
) -> dict[str, Any]:
    """Overlay embedded resources with their latest canonical vault copies."""

    subject = deepcopy(stored_subject)

    def hydrate(resource: dict[str, Any]) -> dict[str, Any]:
        current = deepcopy(resource)
        resource_type = str(current.get("resourceType", "") or "").strip()
        resource_id = str(current.get("id", "") or "").strip()
        if resource_type != "ResearchSubject" and resource_type and resource_id:
            canonical = vault_repo.get(vault_id, resource_id, resource_type)
            if isinstance(canonical, dict):
                current = deepcopy(canonical)
        contained = current.get("contained")
        if isinstance(contained, list):
            current["contained"] = [
                hydrate(item) if isinstance(item, dict) else item for item in contained
            ]
        return current

    return hydrate(subject)


class _BufferedFeedbackSink:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def submit(self, event: dict[str, Any]) -> None:
        self.events.append(event)


class ResearchCodingReviewManager:
    """Read and resolve durable study drafts without depending on job retention."""

    def __init__(self, deps: ApiManagerDependencies) -> None:
        self._deps = deps

    def _authorize(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Any,
        study: str,
    ) -> str:
        _enforce_supported_scope(jurisdiction, sector, self._deps.settings)
        auth_header = str(getattr(request, "headers", {}).get("authorization", "") or "")
        _enforce_auth_context(
            {},
            self._deps.settings,
            authorization_header=auth_header,
            require_token=True,
            required_scopes={"dataconv.review"},
            expected_organization=tenant_id,
            expected_research_study=study,
            require_study_research=sector_requires_professional_research_auth(
                sector,
                self._deps.settings,
            ),
        )
        return build_storage_namespace(
            network_kind=self._deps.settings.network_mode,
            jurisdiction=jurisdiction,
            sector=sector,
            tenant_id=tenant_id,
        )

    def search_pending(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Any,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        values = _parameter_values(body if isinstance(body, dict) else {})
        study = _study_from_reference(values.get("study"))
        count = _integer_parameter(values, "_count", 100)
        offset = _integer_parameter(values, "_offset", 0)
        if count < 1 or count > 100:
            raise HTTPException(status_code=400, detail="_count must be between 1 and 100")
        if offset < 0:
            raise HTTPException(status_code=400, detail="_offset must be zero or greater")
        vault_id = self._authorize(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            request=request,
            study=study,
        )
        subjects = self._deps.vault_repo.query(
            vault_id,
            {RESEARCH_SUBJECT_STUDY_CLAIM: study},
            "ResearchSubject",
        )
        # Most study rows are already published or never needed coding review.
        # Hydrate canonical children only for aggregates that advertise pending
        # proposals, avoiding an N+1 read across the complete study.
        pending = [
            _hydrate_subject(self._deps.vault_repo, vault_id, subject)
            for subject in subjects
            if _has_pending(subject)
        ]
        pending = [subject for subject in pending if _has_pending(subject)]
        pending.sort(key=lambda subject: str(subject.get("id", "")))
        page = pending[offset : offset + count]
        return {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": len(pending),
            "entry": [
                {
                    "fullUrl": f"ResearchSubject/{subject.get('id', '')}",
                    "resource": subject,
                }
                for subject in page
            ],
        }

    def search_candidates(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Any,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Search governed terminology and attach results to one pending proposal."""

        payload = body if isinstance(body, dict) else {}
        study = _study_from_reference(payload.get("researchStudy"))
        vault_id = self._authorize(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            request=request,
            study=study,
        )
        terminology = self._deps.terminology_client
        if terminology is None:
            raise HTTPException(status_code=503, detail="terminology service is not configured")
        resource_type = str(payload.get("resourceType", "") or "").strip()
        resource_id = str(payload.get("resourceId", "") or "").strip()
        proposal_id = str(payload.get("proposalId", "") or "").strip()
        text = str(payload.get("text", "") or "").strip()
        language = str(payload.get("language", "") or "").strip()
        raw_sources = payload.get("sources", [])
        if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", resource_type) or not resource_id or not proposal_id:
            raise HTTPException(status_code=400, detail="resource and proposal identity are required")
        if len(text) < 2 or len(text) > 160:
            raise HTTPException(status_code=400, detail="text must contain between 2 and 160 characters")
        if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language):
            raise HTTPException(status_code=400, detail="language must be a valid BCP 47 tag")
        if not isinstance(raw_sources, list) or len(raw_sources) > 10:
            raise HTTPException(status_code=400, detail="sources must be a bounded list")
        sources = tuple(str(value or "").strip() for value in raw_sources)
        if any(not re.fullmatch(r"[A-Z][A-Z0-9_]{1,31}", value) for value in sources):
            raise HTTPException(status_code=400, detail="source is invalid")

        subjects = self._deps.vault_repo.query(
            vault_id,
            {RESEARCH_SUBJECT_STUDY_CLAIM: study},
            "ResearchSubject",
        )
        for stored_subject in subjects:
            subject = _hydrate_subject(self._deps.vault_repo, vault_id, stored_subject)
            resource = next((item for item in _resources(subject)
                if str(item.get("resourceType", "")) == resource_type
                and str(item.get("id", "")) == resource_id), None)
            if resource is None:
                continue
            meta = resource.get("meta")
            proposals = meta.get("codingProposals") if isinstance(meta, dict) else None
            proposal = next((item for item in proposals or []
                if isinstance(item, dict) and str(item.get("id", "")) == proposal_id), None)
            if proposal is None or str(proposal.get("status", "")) != "proposed":
                continue
            field = str(proposal.get("field", "") or "").strip()
            if not re.fullmatch(rf"{re.escape(resource_type)}\.(?:code|[a-z][a-z0-9-]*-code)", field):
                raise HTTPException(status_code=409, detail="proposal field does not match the resource")
            found = terminology.search(TerminologySearchRequest(
                text=text,
                language=language,
                fhir_version="R4",
                sector=sector,
                jurisdiction=jurisdiction,
                resource_type=resource_type,
                field=field,
                sources=sources,
                limit=50,
            ))
            merged = {
                str(item.get("id", "")): item
                for item in proposal.get("candidates", [])
                if isinstance(item, dict) and str(item.get("id", ""))
            }
            for value in found:
                candidate = _candidate(resource_type, field, value)
                merged[candidate["id"]] = candidate
            proposal["candidates"] = list(merged.values())
            self._deps.vault_repo.put(vault_id, [resource], resource_type)
            self._deps.vault_repo.put(vault_id, [subject], "ResearchSubject")
            return {
                "proposalId": proposal_id,
                "resourceType": resource_type,
                "resourceId": resource_id,
                "field": field,
                "query": {"text": text, "language": language, "sources": list(sources)},
                "candidates": proposal["candidates"],
            }
        raise HTTPException(status_code=404, detail="pending coding proposal was not found in the authorized study")

    def reclassify_pending(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Any,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Move one unresolved local text proposal to an explicit FHIR target."""

        payload = body if isinstance(body, dict) else {}
        study = _study_from_reference(payload.get("researchStudy"))
        vault_id = self._authorize(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            request=request,
            study=study,
        )
        source_type = str(payload.get("resourceType", "") or "").strip()
        source_id = str(payload.get("resourceId", "") or "").strip()
        proposal_id = str(payload.get("proposalId", "") or "").strip()
        target_type = str(payload.get("targetResourceType", "") or "").strip()
        target_field = str(payload.get("targetField", "") or "").strip()
        target_profile = _RECLASSIFICATION_TARGETS.get((target_type, target_field))
        if (
            not re.fullmatch(r"[A-Z][A-Za-z0-9]*", source_type)
            or not source_id
            or not proposal_id
            or target_profile is None
        ):
            raise HTTPException(status_code=400, detail="coding proposal reclassification target is invalid")

        subjects = self._deps.vault_repo.query(
            vault_id,
            {RESEARCH_SUBJECT_STUDY_CLAIM: study},
            "ResearchSubject",
        )
        for stored_subject in subjects:
            subject = _hydrate_subject(self._deps.vault_repo, vault_id, stored_subject)
            contained = subject.get("contained")
            if not isinstance(contained, list):
                continue
            source = next((
                resource for resource in contained
                if isinstance(resource, dict)
                and str(resource.get("resourceType", "")) == source_type
                and str(resource.get("id", "")) == source_id
            ), None)
            if source is None:
                continue
            source_meta = source.get("meta")
            proposals = source_meta.get("codingProposals") if isinstance(source_meta, dict) else None
            proposal = next((
                item for item in proposals or []
                if isinstance(item, dict)
                and str(item.get("id", "")) == proposal_id
                and str(item.get("status", "")) == "proposed"
            ), None)
            if proposal is None:
                continue
            input_text = str(proposal.get("inputText", "") or "").strip()
            language = str(proposal.get("language", "") or "und").strip() or "und"
            if not input_text:
                raise HTTPException(status_code=409, detail="coding proposal has no local text")
            subject_id = str(subject.get("id", "") or "").strip()
            target_id = stable_uuid(vault_id, subject_id, "reclassified", proposal_id, target_type, target_field)
            target_claims = {
                "@context": FHIR_API_CONTEXT,
                str(target_profile["identifier"]): target_id,
                str(target_profile["subject"]): f"ResearchSubject/{subject_id}",
                f"{target_type}.language": language,
                f"{target_field}-text": input_text,
                **dict(target_profile["status"]),
            }
            moved_proposal = deepcopy(proposal)
            moved_proposal["field"] = target_field
            moved_proposal["candidates"] = []
            moved_proposal.pop("selectedCandidateId", None)
            moved_proposal.pop("userSelected", None)
            moved_proposal.pop("reviewedAt", None)
            moved_proposal["reclassifiedFrom"] = {
                "resourceType": source_type,
                "resourceId": source_id,
                "field": str(proposal.get("field", "") or ""),
            }
            target = {
                "resourceType": target_type,
                "id": target_id,
                "meta": {"claims": target_claims, "codingProposals": [moved_proposal]},
            }

            remaining_proposals = [item for item in proposals or [] if item is not proposal]
            source_claims = _resource_claims(source)
            source_claims.pop(f"{str(proposal.get('field', '') or '')}-text", None)
            source_meta["codingProposals"] = remaining_proposals
            meaningful_source_claims = [
                key for key, value in source_claims.items()
                if key != "@context" and str(value or "").strip()
            ]
            remove_source = not remaining_proposals and not meaningful_source_claims

            updated_contained = [
                item for item in contained
                if not remove_source or item is not source
            ]
            updated_contained.append(target)
            subject["contained"] = updated_contained

            for resource in updated_contained:
                if not isinstance(resource, dict) or str(resource.get("resourceType", "")) != "Composition":
                    continue
                claims = _resource_claims(resource)
                entry_ids = _reference_ids(claims.get("Composition.entry"))
                if source_id not in entry_ids:
                    continue
                replacement = [target_id if entry_id == source_id and remove_source else entry_id for entry_id in entry_ids]
                if not remove_source:
                    replacement.append(target_id)
                claims["Composition.entry"] = ",".join(f"urn:uuid:{entry_id}" for entry_id in dict.fromkeys(replacement))
                self._deps.vault_repo.put(vault_id, [resource], "Composition")

            self._deps.vault_repo.put(vault_id, [target], target_type)
            if remove_source:
                self._deps.vault_repo.delete(vault_id, source_id, source_type)
            else:
                self._deps.vault_repo.put(vault_id, [source], source_type)
            self._deps.vault_repo.put(vault_id, [subject], "ResearchSubject")
            return {
                "proposalId": proposal_id,
                "resourceType": target_type,
                "resourceId": target_id,
                "field": target_field,
            }
        raise HTTPException(status_code=404, detail="pending coding proposal was not found in the authorized study")

    def discard_pending_import(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Any,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Discard the still-unreviewed draft graph for one exact import thread."""

        payload = body if isinstance(body, dict) else {}
        study = _study_from_reference(payload.get("researchStudy"))
        thid = str(payload.get("thid", "") or "").strip()
        if not thid or len(thid) > 200:
            raise HTTPException(status_code=400, detail="thid is required")
        vault_id = self._authorize(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            request=request,
            study=study,
        )
        discarded_subjects = 0
        discarded_resources = 0
        subjects = self._deps.vault_repo.query(
            vault_id,
            {RESEARCH_SUBJECT_STUDY_CLAIM: study},
            "ResearchSubject",
        )
        for stored_subject in subjects:
            subject = _hydrate_subject(self._deps.vault_repo, vault_id, stored_subject)
            contained = subject.get("contained")
            if not isinstance(contained, list):
                continue
            compositions = [
                item for item in contained
                if isinstance(item, dict)
                and str(item.get("resourceType", "")) == "Composition"
                and str(_resource_claims(item).get("Composition.relatesto-target", "")) == thid
            ]
            if not compositions:
                continue
            entry_ids = {
                entry_id
                for composition in compositions
                for entry_id in _reference_ids(_resource_claims(composition).get("Composition.entry"))
            }
            entries = [
                item for item in contained
                if isinstance(item, dict) and str(item.get("id", "")) in entry_ids
            ]
            proposals = [proposal for resource in entries for proposal in _pending_proposals(resource)]
            has_resolved = any(
                isinstance(proposal, dict) and str(proposal.get("status", "")) != "proposed"
                for resource in entries
                for proposal in (resource.get("meta", {}).get("codingProposals", []) or [])
            )
            if not proposals or has_resolved:
                raise HTTPException(status_code=409, detail="only an entirely pending import draft can be discarded")
            removed_ids = entry_ids | {str(item.get("id", "")) for item in compositions}
            subject["contained"] = [
                item for item in contained
                if not isinstance(item, dict) or str(item.get("id", "")) not in removed_ids
            ]
            subject_id = str(subject.get("id", "") or "")
            for composition in compositions:
                claims = _resource_claims(composition)
                section = _safe_token(str(claims.get("Composition.section", "")).split("|")[-1])
                link_section = f"{subject_id}_{section}"
                for entry_id in _reference_ids(claims.get("Composition.entry")):
                    self._deps.vault_repo.delete(vault_id, entry_id, link_section)
            for resource in [*compositions, *entries]:
                resource_type = str(resource.get("resourceType", "") or "")
                resource_id = str(resource.get("id", "") or "")
                if resource_type and resource_id:
                    self._deps.vault_repo.delete(vault_id, resource_id, resource_type)
                    self._deps.search_repo.delete(
                        vault_id=vault_id,
                        resource_type=resource_type,
                        resource_id=resource_id,
                    )
            if subject["contained"]:
                self._deps.vault_repo.put(vault_id, [subject], "ResearchSubject")
            else:
                self._deps.vault_repo.delete(vault_id, subject_id, "ResearchSubject")
                self._deps.search_repo.delete(
                    vault_id=vault_id,
                    resource_type="ResearchSubject",
                    resource_id=subject_id,
                )
            discarded_subjects += 1
            discarded_resources += len(removed_ids)
        if discarded_subjects == 0:
            raise HTTPException(status_code=404, detail="pending import draft was not found for thid")
        return {
            "thid": thid,
            "discardedSubjectCount": discarded_subjects,
            "discardedResourceCount": discarded_resources,
        }

    def prepare_pending(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Any,
        body: dict[str, Any],
    ) -> dict[str, int]:
        """Materialize review proposals for durable local `*-text` claims."""

        values = _parameter_values(body if isinstance(body, dict) else {})
        study = _study_from_reference(values.get("study"))
        vault_id = self._authorize(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            request=request,
            study=study,
        )
        terminology = self._deps.terminology_client
        if terminology is None:
            raise HTTPException(status_code=503, detail="terminology service is not configured")
        subjects = self._deps.vault_repo.query(
            vault_id,
            {RESEARCH_SUBJECT_STUDY_CLAIM: study},
            "ResearchSubject",
        )
        lookups: dict[tuple[str, str, str, str], TerminologySearchRequest] = {}
        targets: list[tuple[
            dict[str, Any], dict[str, Any], list[dict[str, Any]], str, str,
            str, str, str, dict[str, Any],
        ]] = []
        prepared: list[dict[str, Any]] = []
        prepared_subjects = 0
        proposal_count = 0
        candidate_count = 0
        for stored_subject in subjects:
            subject = deepcopy(stored_subject)
            subject_claims = subject.get("meta", {}).get("claims", {})
            language = str(subject_claims.get("Subject.language", "und") or "und").strip()
            _backfill_immunizations_from_imported_documents(
                subject,
                vault_id=vault_id,
                default_language=language,
            )
            resources = _resources(subject)
            for resource in resources[1:]:
                resource_type = str(resource.get("resourceType", "") or "").strip()
                resource_id = str(resource.get("id", "") or "").strip()
                meta = resource.get("meta")
                if not resource_type or not resource_id or not isinstance(meta, dict):
                    continue
                claims = meta.get("claims")
                if not isinstance(claims, dict):
                    continue
                proposals = meta.get("codingProposals")
                if not isinstance(proposals, list):
                    proposals = []
                    meta["codingProposals"] = proposals
                represented = {
                    str(item.get("field", "")) for item in proposals if isinstance(item, dict)
                }
                for claim_key, raw_text in claims.items():
                    key = str(claim_key or "").strip()
                    text = str(raw_text or "").strip()
                    if not key.endswith("-text") or not text:
                        continue
                    field = key.removesuffix("-text")
                    if field in represented or not re.fullmatch(
                        rf"{re.escape(resource_type)}\.(?:code|[a-z][a-z0-9-]*-code)",
                        field,
                    ):
                        continue
                    lookup = (resource_type, field, text, language)
                    if lookup not in lookups:
                        lookups[lookup] = TerminologySearchRequest(
                            text=text,
                            language=language,
                            fhir_version="R4",
                            sector=sector,
                            jurisdiction=jurisdiction,
                            resource_type=resource_type,
                            field=field,
                        )
                    targets.append((
                        subject, resource, proposals, resource_type, resource_id,
                        field, text, language, subject_claims,
                    ))
                    represented.add(field)

        lookup_items = list(lookups.items())
        candidate_cache: dict[tuple[str, str, str, str], list[TerminologyCandidate]] = {}
        if lookup_items:
            def safe_search(search_request: TerminologySearchRequest) -> list[TerminologyCandidate]:
                try:
                    return terminology.search(search_request)
                except Exception:
                    # A terminology outage or an unavailable species filter
                    # must not hide the imported local text from human review.
                    return []

            with ThreadPoolExecutor(max_workers=min(8, len(lookup_items))) as executor:
                candidate_lists = executor.map(
                    safe_search,
                    (request for _, request in lookup_items),
                )
                candidate_cache = {
                    key: candidates for (key, _), candidates in zip(lookup_items, candidate_lists)
                }

        changed_subject_ids: set[str] = set()
        for subject, resource, proposals, resource_type, resource_id, field, text, language, subject_claims in targets:
            candidates = candidate_cache[(resource_type, field, text, language)]
            proposal_id = stable_uuid(
                vault_id,
                resource_type,
                resource_id,
                "coding-proposal",
                field,
                text,
            )
            proposals.append({
                "id": proposal_id,
                "status": "proposed",
                "field": field,
                "inputText": text,
                "language": language,
                "fhirVersion": "R4",
                "sector": sector,
                "jurisdiction": jurisdiction,
                "subjectKind": "animal" if sector.startswith("animal") else "person",
                "rowContext": {
                    "species": str(subject_claims.get("Subject.animal-species", "") or ""),
                    "breed": str(subject_claims.get("Subject.animal-breed", "") or ""),
                },
                "candidates": [_candidate(resource_type, field, candidate) for candidate in candidates],
            })
            proposal_count += 1
            candidate_count += len(candidates)
            subject_id = str(subject.get("id", "") or "")
            if subject_id not in changed_subject_ids:
                changed_subject_ids.add(subject_id)
                prepared.append(subject)

        prepared_subjects = len(prepared)
        if prepared:
            self._deps.vault_repo.put(vault_id, prepared, "ResearchSubject")
            contained_by_type: dict[str, list[dict[str, Any]]] = {}
            for subject in prepared:
                for resource in _resources(subject)[1:]:
                    resource_type = str(resource.get("resourceType", "") or "").strip()
                    if resource_type:
                        contained_by_type.setdefault(resource_type, []).append(resource)
            for resource_type, resources in contained_by_type.items():
                self._deps.vault_repo.put(vault_id, resources, resource_type)
        return {
            "preparedSubjectCount": prepared_subjects,
            "proposalCount": proposal_count,
            "candidateCount": candidate_count,
        }

    def apply_reviews(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Any,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        payload = body if isinstance(body, dict) else {}
        study = _study_from_reference(payload.get("researchStudy"))
        vault_id = self._authorize(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            request=request,
            study=study,
        )
        raw_reviews = payload.get("codingReviews")
        if not isinstance(raw_reviews, list) or not raw_reviews:
            raise HTTPException(status_code=400, detail="codingReviews must contain at least one review")
        reviews = [item for item in raw_reviews if isinstance(item, dict)]
        if len(reviews) != len(raw_reviews) or len(reviews) > 100:
            raise HTTPException(status_code=400, detail="codingReviews must contain between 1 and 100 objects")

        subjects = self._deps.vault_repo.query(
            vault_id,
            {RESEARCH_SUBJECT_STUDY_CLAIM: study},
            "ResearchSubject",
        )
        remaining = list(reviews)
        reviewed_count = 0
        promoted_count = 0
        pending_subject_count = 0
        buffered_feedback = _BufferedFeedbackSink()
        prepared: list[tuple[dict[str, Any], list[dict[str, Any]], bool]] = []

        for stored_subject in subjects:
            stored_resources = _resources(stored_subject)
            identities = {
                (str(resource.get("resourceType", "")), str(resource.get("id", "")))
                for resource in stored_resources
            }
            relevant = [
                review for review in remaining
                if (str(review.get("resourceType", "")), str(review.get("resourceId", ""))) in identities
            ]
            if relevant:
                subject = _hydrate_subject(self._deps.vault_repo, vault_id, stored_subject)
                resources = _resources(subject)
                try:
                    reviewed_count += apply_coding_reviews(
                        resources=resources,
                        reviews=relevant,
                        feedback_sink=buffered_feedback,
                        reviewer_subject=str(getattr(request, "reviewer_subject", "") or "study-reviewer"),
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
                remaining = [review for review in remaining if review not in relevant]
                pending = _has_pending(subject)
                prepared.append((subject, resources, pending))
            else:
                pending = _has_pending(stored_subject)
            if pending:
                pending_subject_count += 1

        if remaining:
            raise HTTPException(status_code=404, detail="coding review resource was not found in the authorized ResearchStudy")

        if prepared:
            self._deps.vault_repo.put(
                vault_id,
                [subject for subject, _, _ in prepared],
                "ResearchSubject",
            )
            contained_by_type: dict[str, list[dict[str, Any]]] = {}
            for _, resources, _ in prepared:
                for resource in resources[1:]:
                    resource_type = str(resource.get("resourceType", "") or "").strip()
                    if resource_type:
                        contained_by_type.setdefault(resource_type, []).append(resource)
            for resource_type, resources in contained_by_type.items():
                self._deps.vault_repo.put(vault_id, resources, resource_type)

        for subject, resources, pending in prepared:
            if not pending:
                for resource in resources:
                    resource_type = str(resource.get("resourceType", "") or "").strip()
                    if resource_type:
                        self._deps.search_repo.upsert(
                            vault_id=vault_id,
                            resource_type=resource_type,
                            resource=resource,
                        )
                promoted_count += 1
        for event in buffered_feedback.events:
            self._deps.coding_feedback_sink.submit(event)
        return {
            "status": "pending-review" if pending_subject_count else "success",
            "reviewedProposalCount": reviewed_count,
            "promotedSubjectCount": promoted_count,
            "pendingSubjectCount": pending_subject_count,
        }
