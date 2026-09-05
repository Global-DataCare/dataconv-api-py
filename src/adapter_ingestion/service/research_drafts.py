# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

from ..runtime import IVaultRepository
from ..runtime.models import now_iso_utc
from .api_support import _compose_software_id_token
from .research import build_storage_namespace
import re

def _safe_token(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "_"
    return re.sub(r"[^a-z0-9._-]+", "_", text)


def _iter_resources(node: Any) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    if not isinstance(node, dict):
        return resources
    resource_type = str(node.get("resourceType", "") or "").strip()
    resource_id = str(node.get("id", "") or "").strip()
    if resource_type and resource_id:
        resources.append(node)
    contained = node.get("contained")
    if isinstance(contained, list):
        for item in contained:
            if isinstance(item, dict):
                resources.extend(_iter_resources(item))
    return resources


def annotate_resource_for_research(resource: dict[str, Any], *, user_selected: bool) -> dict[str, Any]:
    annotated = deepcopy(resource)
    resource_type = str(annotated.get("resourceType", "") or "").strip()
    if not resource_type:
        return annotated
    meta = annotated.get("meta")
    if not isinstance(meta, dict):
        meta = {}
        annotated["meta"] = meta
    claims = meta.get("claims")
    if not isinstance(claims, dict):
        claims = {}
        meta["claims"] = claims
    claims[f"{resource_type}.userSelected"] = str(bool(user_selected)).lower()
    if resource_type == "DocumentReference":
        annotated["docStatus"] = "preliminary"
        claims["DocumentReference.docStatus"] = "preliminary"
    contained = annotated.get("contained")
    if isinstance(contained, list):
        annotated["contained"] = [
            annotate_resource_for_research(item, user_selected=user_selected) if isinstance(item, dict) else item
            for item in contained
        ]
    return annotated


def annotate_composition_message_for_research(
    composition_message: dict[str, Any],
    *,
    user_selected: bool = True,
) -> dict[str, Any]:
    annotated = deepcopy(composition_message)
    body = annotated.get("body")
    if not isinstance(body, dict):
        return annotated
    entries = body.get("data")
    if not isinstance(entries, list):
        return annotated
    updated_entries: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        updated = dict(entry)
        resource = entry.get("resource")
        if isinstance(resource, dict):
            updated["resource"] = annotate_resource_for_research(resource, user_selected=user_selected)
        updated_entries.append(updated)
    body["data"] = updated_entries
    return annotated


def persist_research_drafts(
    *,
    vault_repo: IVaultRepository,
    job: Any,
    network_kind: str,
    jurisdiction: str,
    composition_message: dict[str, Any],
) -> int:
    tenant_id = str(job.request.alternate_name or "").strip()
    vault_id = build_storage_namespace(
        network_kind=network_kind,
        jurisdiction=jurisdiction,
        sector=str(job.request.sector or "onehealth-research"),
        tenant_id=tenant_id,
    )
    body = composition_message.get("body")
    if not isinstance(body, dict):
        return 0
    entries = body.get("data")
    if not isinstance(entries, list):
        return 0

    persisted = 0
    # First pass: collect all resources by ID and save them to /vaultId/resourceType
    all_resources: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        resource = entry.get("resource")
        if not isinstance(resource, dict):
            continue
        for item in _iter_resources(resource):
            resource_type = str(item.get("resourceType", "") or "").strip()
            resource_id = str(item.get("id", "") or "").strip()
            if not resource_type or not resource_id:
                continue
            
            if resource_type == "Composition":
                meta = item.get("meta")
                if not isinstance(meta, dict):
                    meta = {}
                    item["meta"] = meta
                claims = meta.get("claims")
                if not isinstance(claims, dict):
                    claims = {}
                    meta["claims"] = claims
                claims["Composition.relatesto-target"] = str(job.thid or "").strip()
                claims["Composition.relatesto-type"] = "part-of"
                
            all_resources[resource_id] = deepcopy(item)
            vault_repo.put(vault_id, [item], resource_type)
            persisted += 1

    # Second pass: find Compositions, extract claims, and save links
    for res_id, item in all_resources.items():
        if str(item.get("resourceType", "")) == "Composition":
            claims = item.get("meta", {}).get("claims", {})
            if not isinstance(claims, dict):
                continue
            
            raw_subject = str(claims.get("Composition.subject", "")).strip()
            if not raw_subject:
                continue
            subject_id = raw_subject.split(":")[-1]

            raw_section = str(claims.get("Composition.section", "")).strip()
            if not raw_section:
                continue
            section_id = _safe_token(raw_section.split("|")[-1])

            raw_entries = str(claims.get("Composition.entry", "")).strip()
            if not raw_entries:
                continue
            
            entry_ids = [e.split(":")[-1] for e in raw_entries.split(",") if e.strip()]
            
            # Save referenced items in the link section
            link_section = f"{subject_id}_{section_id}"
            linked_docs = []
            for e_id in entry_ids:
                if e_id in all_resources:
                    linked_docs.append(all_resources[e_id])
                else:
                    # Create a stub if the resource wasn't found in the bundle (rare but possible)
                    linked_docs.append({"id": e_id, "resourceType": "LinkStub", "ref": e_id})
            
            if linked_docs:
                vault_repo.put(vault_id, linked_docs, link_section)

    return persisted


# TODO(dataconv-api-py): reviewed promotion should update the same resources
# by flipping `userSelected` to `false` and then emit the downstream batch order for
# `/{tenant-id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{subjectKind}/{resourceType}/_batch`.
# The integration hook belongs right after review persistence, before gateway publication.
