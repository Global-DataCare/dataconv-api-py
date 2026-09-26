# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import re
from typing import Any

from ...ai.terminology import TerminologyCandidate, TerminologySearchRequest
from ...models import stable_uuid
from ..api_support import HTTPException, _enforce_auth_context, _enforce_supported_scope
from ..coding_review import apply_coding_reviews, has_pending_coding_proposals
from ..research import build_storage_namespace
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
            with ThreadPoolExecutor(max_workers=min(8, len(lookup_items))) as executor:
                candidate_lists = executor.map(
                    terminology.search,
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
