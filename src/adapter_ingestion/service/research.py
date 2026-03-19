# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
import uuid


DEFAULT_SECTOR = "onehealth-research"
DEFAULT_UPLOAD_RESOURCE_TYPE = "Bundle"


def normalize_tenant_id(value: str) -> str:
    return str(value or "").strip()


def normalize_sector(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return DEFAULT_SECTOR
    return re.sub(r"[^a-z0-9._-]+", "-", text).strip("-") or DEFAULT_SECTOR


def build_vault_id(*, sector: str, tenant_id: str) -> str:
    tenant_token = normalize_tenant_id(tenant_id)
    if not tenant_token:
        raise ValueError("tenant_id is required")
    return f"{normalize_sector(sector)}_{tenant_token}"


def build_research_draft_id(*, vault_id: str, resource_type: str, resource_id: str) -> str:
    seed = "|".join(
        [
            "research-draft",
            str(vault_id or "").strip(),
            str(resource_type or "").strip(),
            str(resource_id or "").strip(),
        ]
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def build_config_create_response_path(
    *,
    jurisdiction: str,
    sector: str,
    tenant_id: str,
    software_id: str,
    thid: str,
) -> str:
    return (
        f"/host/cds-{jurisdiction}/v1/{normalize_sector(sector)}/{tenant_id}/{software_id}/config/_create-response"
        f"?thid={thid}"
    )


def build_upload_response_path(
    *,
    jurisdiction: str,
    sector: str,
    tenant_id: str,
    software_id: str,
    resource_type: str,
    thid: str,
) -> str:
    return (
        f"/{tenant_id}/cds-{jurisdiction}/v1/{normalize_sector(sector)}/digitaltwin/"
        f"{software_id}/{resource_type}/_upload-response?thid={thid}"
    )
