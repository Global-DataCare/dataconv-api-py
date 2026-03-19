# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from ..api_support import (
    HTTPException,
    _enforce_auth_context,
    _extract_iss,
    _extract_query_value,
    _extract_required_type,
    _require_epoch_seconds,
    _validate_public_iss,
)
from ..observability import log_event
from ..research import build_vault_id
from .dependencies import ApiManagerDependencies


def promote_resources(
    *,
    deps: ApiManagerDependencies,
    tenant_id: str,
    sector: str,
    resource_type: str,
    request: Any,
    body: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    payload = body if isinstance(body, dict) else {}
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
    for comp in compositions:
        comp_claim_key = f"{governed_resource_type}.userSelected"
        is_draft = str(comp.get("meta", {}).get("claims", {}).get(comp_claim_key, "")).lower()
        if is_draft == "true":
            comp.setdefault("meta", {}).setdefault("claims", {})[comp_claim_key] = "false"
            deps.vault_repo.put(vault_id, [comp], governed_resource_type)
            deps.search_repo.upsert(vault_id=vault_id, resource_type=governed_resource_type, resource=comp)
            promoted_count += 1

        subject = str(comp.get("meta", {}).get("claims", {}).get("Composition.subject", "")).strip().split(":")[-1]
        section = str(comp.get("meta", {}).get("claims", {}).get("Composition.section", "")).strip().split("|")[-1]
        if not subject or not section:
            continue
        link_section = f"{subject}_{section}"
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
                promoted_count += 1

    log_event(
        "research_drafts_promoted",
        source=source,
        thid=thid,
        vaultId=vault_id,
        promotedCount=promoted_count,
    )

    return {
        "type": "https://didcomm.org/plaintext/2.0/message",
        "thid": thid,
        "body": {
            "status": "success",
            "promotedCount": promoted_count,
            "message": f"Promoted {promoted_count} resources to userSelected=false",
        },
    }
