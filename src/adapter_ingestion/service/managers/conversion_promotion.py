# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..api_support import (
    HTTPException,
    _enforce_auth_context,
    _extract_iss,
    _extract_query_value,
    _extract_required_type,
    _enforce_supported_scope,
    _require_epoch_seconds,
    _validate_public_iss,
)
from ..observability import log_event
from ..research import build_storage_namespace
from .dependencies import ApiManagerDependencies
from ..coding_review import apply_coding_reviews
from ..research_study import RESEARCH_SUBJECT_STUDY_CLAIM
from ..research_study import research_study_reference as optional_research_study_reference


def _build_operation_outcome(*, message: str, diagnostics: str) -> dict[str, Any]:
    return {
        "resourceType": "OperationOutcome",
        "issue": [
            {
                "severity": "information",
                "code": "informational",
                "details": {"text": message},
                "diagnostics": diagnostics,
            }
        ],
    }


def _build_dcat_dataset(
    *,
    tenant_id: str,
    sector: str,
    jurisdiction: str,
    resource_type: str,
    thid: str,
    index: int,
) -> dict[str, Any]:
    identifier = f"{tenant_id}:{resource_type}:{thid}:{index}"
    return {
        "@context": "https://www.w3.org/ns/dcat",
        "@type": "dcat:Dataset",
        "dct:identifier": identifier,
        "dct:title": f"{tenant_id} — {resource_type} actualizado",
        "dct:description": (
            f"Dataset actualizado en la fase de confirmación para {resource_type} "
            f"(thid={thid})."
        ),
        "dct:publisher": {
            "@id": f"urn:org:{tenant_id}",
            "foaf:name": tenant_id,
        },
        "dcat:distribution": [
            {
                "@type": "dcat:Distribution",
                "dct:format": "application/fhir+json",
                "dcat:accessURL": (
                    f"https://globaldatacare.es/publisher/cds-{jurisdiction}/v1/"
                    f"{sector}/{tenant_id}/dataset/{resource_type}/_search"
                ),
            }
        ],
    }


def promote_resources(
    *,
    deps: ApiManagerDependencies,
    tenant_id: str,
    jurisdiction: str,
    sector: str,
    resource_type: str,
    request: Any,
    body: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    payload = body if isinstance(body, dict) else {}
    _enforce_supported_scope(jurisdiction, sector, deps.settings)
    issuer = _extract_iss(payload)
    if not issuer:
        raise HTTPException(status_code=400, detail="iss is required in DIDComm payload")
    _validate_public_iss(issuer)
    didcomm_type = _extract_required_type(payload)
    if not didcomm_type:
        raise HTTPException(status_code=400, detail="type is required in DIDComm payload")
    issued_at = _require_epoch_seconds(payload, "iat")
    expires_at = _require_epoch_seconds(payload, "exp")
    if expires_at < issued_at:
        raise HTTPException(status_code=400, detail="exp must be greater than or equal to iat")

    auth_header = ""
    try:
        auth_header = str(request.headers.get("authorization", "") or "")
    except Exception:
        auth_header = ""
    _enforce_auth_context(
        payload,
        deps.settings,
        authorization_header=auth_header,
        expected_organization=tenant_id,
    )

    payload_thid = str(payload.get("thid", "")).strip()
    query_thid = _extract_query_value(request, "thid")
    if payload_thid and query_thid and payload_thid != query_thid:
        raise HTTPException(status_code=400, detail="thid mismatch between DIDComm payload and query parameter")
    thid = payload_thid or query_thid
    if not thid:
        raise HTTPException(status_code=400, detail="thid is required in DIDComm payload or query")
    try:
        requested_study = optional_research_study_reference(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = deps.control_plane.get_job_by_thid(thid)
    if not job:
        raise HTTPException(status_code=404, detail="conversion thread not found")
    research_study_reference = str(job.request.research_study_reference or "").strip()
    if str(sector or "").strip().lower() == "onehealth-research" and not research_study_reference:
        raise HTTPException(status_code=409, detail="legacy research conversion has no ResearchStudy context")
    if research_study_reference and not requested_study:
        raise HTTPException(status_code=400, detail="researchStudy.reference is required")
    if requested_study and requested_study != research_study_reference:
        raise HTTPException(status_code=404, detail="conversion thread not found for researchStudy.reference")

    vault_id = build_storage_namespace(
        network_kind=deps.settings.network_mode,
        jurisdiction=jurisdiction,
        sector=sector,
        tenant_id=tenant_id,
    )
    governed_resource_type = str(resource_type or "Composition").strip() or "Composition"

    compositions = deps.vault_repo.query(
        vault_id,
        {f"{governed_resource_type}.relatesto-target": thid},
        governed_resource_type,
    )
    if not compositions and governed_resource_type != "Composition":
        compositions = deps.vault_repo.query(
            vault_id,
            {"Composition.relatesto-target": thid},
            "Composition",
        )
        governed_resource_type = "Composition"
    if not compositions:
        raise HTTPException(status_code=404, detail="no composition found for the given thid")

    promoted_count = 0
    promoted_by_type: dict[str, int] = {}
    message_body = payload.get("body", {})
    coding_reviews = (
        message_body.get("codingReviews", []) if isinstance(message_body, dict) else []
    )
    if not isinstance(coding_reviews, list):
        raise HTTPException(status_code=400, detail="body.codingReviews must be an array")
    pending_reviews = [item for item in coding_reviews if isinstance(item, dict)]

    def _mark_promoted(resource_type_key: str) -> None:
        nonlocal promoted_count
        promoted_count += 1
        normalized = str(resource_type_key or "").strip() or "Unknown"
        promoted_by_type[normalized] = int(promoted_by_type.get(normalized, 0) or 0) + 1

    for comp in compositions:
        comp_claim_key = f"{governed_resource_type}.userSelected"
        is_draft = str(comp.get("meta", {}).get("claims", {}).get(comp_claim_key, "")).lower()
        if is_draft == "true":
            comp.setdefault("meta", {}).setdefault("claims", {})[comp_claim_key] = "false"
            deps.vault_repo.put(vault_id, [comp], governed_resource_type)
            deps.search_repo.upsert(vault_id=vault_id, resource_type=governed_resource_type, resource=comp)
            _mark_promoted(governed_resource_type)

        subject = str(comp.get("meta", {}).get("claims", {}).get("Composition.subject", "")).strip().split(":")[-1]
        section = str(comp.get("meta", {}).get("claims", {}).get("Composition.section", "")).strip().split("|")[-1]
        if not subject or not section:
            continue
        link_section = f"{subject}_{section}"

        subject_resource_type = "ResearchSubject"
        subject_res = deps.vault_repo.get(vault_id, subject, subject_resource_type)
        if not subject_res:
            subject_resource_type = "Subject"
            subject_res = deps.vault_repo.get(vault_id, subject, subject_resource_type)
        if subject_res:
            subject_study = str(
                subject_res.get("meta", {}).get("claims", {}).get(RESEARCH_SUBJECT_STUDY_CLAIM, "")
            ).strip()
            if subject_resource_type == "ResearchSubject" and subject_study != research_study_reference:
                raise HTTPException(status_code=409, detail="ResearchSubject.study does not match conversion thread")
            subject_claim_key = f"{subject_resource_type}.userSelected"
            is_subject_draft = str(subject_res.get("meta", {}).get("claims", {}).get(subject_claim_key, "")).lower()
            if is_subject_draft == "true":
                subject_res.setdefault("meta", {}).setdefault("claims", {})[subject_claim_key] = "false"
                deps.vault_repo.put(vault_id, [subject_res], subject_resource_type)
                deps.search_repo.upsert(
                    vault_id=vault_id,
                    resource_type=subject_resource_type,
                    resource=subject_res,
                )
                _mark_promoted(subject_resource_type)

        raw_entries = str(comp.get("meta", {}).get("claims", {}).get("Composition.entry", "")).strip()
        if not raw_entries:
            continue
        entry_ids = [entry.split(":")[-1] for entry in raw_entries.split(",") if entry.strip()]
        for entry_id in entry_ids:
            link_doc = deps.vault_repo.get(vault_id, entry_id, link_section)
            if not link_doc:
                continue
            linked_resource_type = str(link_doc.get("resourceType", "") or "").strip()
            if not linked_resource_type or linked_resource_type == "LinkStub":
                continue
            canon = deps.vault_repo.get(vault_id, entry_id, linked_resource_type)
            if not canon:
                continue
            reviews_for_resource = [
                item
                for item in pending_reviews
                if str(item.get("resourceType", "")) == linked_resource_type
                and str(item.get("resourceId", "")) == entry_id
            ]
            if reviews_for_resource:
                try:
                    apply_coding_reviews(
                        resources=[canon],
                        reviews=reviews_for_resource,
                        feedback_sink=deps.coding_feedback_sink,
                        reviewer_subject=issuer,
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
                pending_reviews = [item for item in pending_reviews if item not in reviews_for_resource]
            res_claim_key = f"{linked_resource_type}.userSelected"
            is_res_draft = str(canon.get("meta", {}).get("claims", {}).get(res_claim_key, "")).lower()
            if is_res_draft == "true":
                canon.setdefault("meta", {}).setdefault("claims", {})[res_claim_key] = "false"
                deps.vault_repo.put(vault_id, [canon], linked_resource_type)
                deps.search_repo.upsert(vault_id=vault_id, resource_type=linked_resource_type, resource=canon)
                _mark_promoted(linked_resource_type)

    if pending_reviews:
        raise HTTPException(status_code=400, detail="one or more coding review resources were not found in the conversion thread")

    log_event(
        "research_drafts_promoted",
        source=source,
        thid=thid,
        vaultId=vault_id,
        promotedCount=promoted_count,
        researchStudyReference=research_study_reference,
    )

    confirmed_at = datetime.now(timezone.utc).isoformat()
    datasets_updated = [
        {"resourceType": resource_type_name, "updatedCount": count}
        for resource_type_name, count in sorted(promoted_by_type.items())
    ]
    dcat_datasets = [
        _build_dcat_dataset(
            tenant_id=tenant_id,
            sector=sector,
            jurisdiction=jurisdiction,
            resource_type=item["resourceType"],
            thid=thid,
            index=idx,
        )
        for idx, item in enumerate(datasets_updated, start=1)
    ]
    diagnostics = (
        f"Confirmación completada para thid={thid}. "
        f"Recursos promovidos={promoted_count}. "
        f"Datasets actualizados={len(datasets_updated)}."
    )
    data_entries = []
    for item, dataset in zip(datasets_updated, dcat_datasets):
        entry_meta = {
            "confirmedAt": confirmed_at,
            "tenantId": tenant_id,
            "jurisdiction": str(jurisdiction or "").upper(),
            "sector": sector,
            "resourceType": item["resourceType"],
            "updatedCount": item["updatedCount"],
        }
        if research_study_reference:
            entry_meta["researchStudy"] = {"reference": research_study_reference}
        data_entries.append({
            "response": {
                "status": "200",
            },
            "meta": entry_meta,
            "resource": dataset,
        })

    return {
        "type": "https://didcomm.org/plaintext/2.0/message",
        "thid": thid,
        "body": {
            "status": "success",
            "promotedCount": promoted_count,
            "message": f"Promoted {promoted_count} resources to userSelected=false",
            "issues": _build_operation_outcome(
                message="Datasets confirmados y actualizados",
                diagnostics=diagnostics,
            ),
            "data": data_entries,
        },
    }
