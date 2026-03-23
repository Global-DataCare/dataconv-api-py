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
from ..research import build_vault_id
from .dependencies import ApiManagerDependencies


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
    _enforce_auth_context(payload, deps.settings, authorization_header=auth_header)

    payload_thid = str(payload.get("thid", "")).strip()
    query_thid = _extract_query_value(request, "thid")
    if payload_thid and query_thid and payload_thid != query_thid:
        raise HTTPException(status_code=400, detail="thid mismatch between DIDComm payload and query parameter")
    thid = payload_thid or query_thid
    if not thid:
        raise HTTPException(status_code=400, detail="thid is required in DIDComm payload or query")

    vault_id = build_vault_id(sector=sector, tenant_id=tenant_id)
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

        subject_res = deps.vault_repo.get(vault_id, subject, "Subject")
        if subject_res:
            subject_claim_key = "Subject.userSelected"
            is_subject_draft = str(subject_res.get("meta", {}).get("claims", {}).get(subject_claim_key, "")).lower()
            if is_subject_draft == "true":
                subject_res.setdefault("meta", {}).setdefault("claims", {})[subject_claim_key] = "false"
                deps.vault_repo.put(vault_id, [subject_res], "Subject")
                deps.search_repo.upsert(vault_id=vault_id, resource_type="Subject", resource=subject_res)
                _mark_promoted("Subject")

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
            res_claim_key = f"{linked_resource_type}.userSelected"
            is_res_draft = str(canon.get("meta", {}).get("claims", {}).get(res_claim_key, "")).lower()
            if is_res_draft == "true":
                canon.setdefault("meta", {}).setdefault("claims", {})[res_claim_key] = "false"
                deps.vault_repo.put(vault_id, [canon], linked_resource_type)
                deps.search_repo.upsert(vault_id=vault_id, resource_type=linked_resource_type, resource=canon)
                _mark_promoted(linked_resource_type)

    log_event(
        "research_drafts_promoted",
        source=source,
        thid=thid,
        vaultId=vault_id,
        promotedCount=promoted_count,
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
    data_entries = [
        {
            "response": {
                "status": "200",
            },
            "meta": {
                "confirmedAt": confirmed_at,
                "tenantId": tenant_id,
                "jurisdiction": str(jurisdiction or "").upper(),
                "sector": sector,
                "resourceType": item["resourceType"],
                "updatedCount": item["updatedCount"],
            },
            "resource": dataset,
        }
        for item, dataset in zip(datasets_updated, dcat_datasets)
    ]

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
