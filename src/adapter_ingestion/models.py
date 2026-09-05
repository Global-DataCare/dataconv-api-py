# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable, Iterable
import uuid


@dataclass(frozen=True)
class AdapterContext:
    manufacturer: str
    tenant_id: str
    jurisdiction: str
    sector: str
    issuer_did: str
    audience_did: str
    language: str = "es-ES"
    gateway_base_url: str = "http://localhost:3000"
    subject_did_prefix: str = "did:web:example.org"
    subject_kind: str = "animal"  # animal | species
    include_fields: tuple[str, ...] = field(default_factory=tuple)
    fhir_species_system: str = "http://hl7.org/fhir/target-species"
    fhir_species_catalog: dict[str, str] = field(default_factory=dict)  # code -> display EN
    species_local_to_fhir: dict[str, str] = field(default_factory=dict)  # local label -> fhir code
    strict_species_mapping: bool = True
    schema_config: dict[str, Any] = field(default_factory=dict)
    personal_id_resolver: Callable[[str], str] | None = None
    embed_xhtml_content: bool = False
    data_use: str = "individual"  # individual | secondary
    log_composition: bool = False


@dataclass(frozen=True)
class CanonicalRecord:
    source_row_number: int
    source_id: str
    timestamp: str
    subject_id: str
    section: str
    family: str
    subfamily: str
    concept: str
    composition_section: str
    document_type_code: str
    attributes: dict[str, str] = field(default_factory=dict)
    species_local: str = ""
    species_fhir_code: str = ""
    subject_birthyear: str = ""
    subject_birthsex: str = ""
    animal_breed_code: str = ""
    animal_gender_status_code: str = ""
    document_category_code: str = ""
    composition_type_code: str = ""
    owner_public_hash: str = ""
    owner_public_name: str = ""
    owner_public_relationship: str = ""
    flat_claims: dict[str, str] = field(default_factory=dict)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(prefix: str, *parts: str) -> str:
    joined = "|".join(str(p).strip() for p in parts if str(p).strip())
    digest = sha256(joined.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}-{digest}"


def stable_uuid(*parts: str) -> str:
    joined = "|".join(str(p).strip() for p in parts if str(p).strip())
    return str(uuid.uuid5(uuid.NAMESPACE_URL, joined))


def jsonapi_resource_entry(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "resource": resource,
    }


def didcomm_plaintext_message(
    thid: str,
    issuer_did: str,
    audience_did: str,
    entries: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    entry_list = list(entries)
    issued_at = int(datetime.now(timezone.utc).timestamp())
    return {
        "jti": str(uuid.uuid4()),
        "thid": thid,
        "type": "https://didcomm.org/plaintext/2.0/message",
        "iss": issuer_did,
        "aud": audience_did,
        "iat": issued_at,
        "exp": issued_at + 300,
        "body": {
            "resourceType": "Bundle",
            "type": "batch",
            "data": entry_list,
            "total": len(entry_list),
        },
    }
