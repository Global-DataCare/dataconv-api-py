# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .settings import ServiceSettings


DEFAULT_SCHEMA_FIELD_MAP = {
    "section": "SECTION",
    "family": "FAMILY",
    "subfamily": "SUBFAMILY",
    "concept": "CONCEPT",
    "subjectId": "SUBJECT_ID",
    "owner": "OWNER",
    "ownerId": "OWNER_ID",
    "species": "SPECIES",
    "breed": "BREED",
    "genderStatus": "GENDER_STATUS",
    "date": "DATE",
    "time": "TIME",
}

DEFAULT_INCLUDE_FIELDS = (
    "DATE",
    "CONCEPT",
    "SECTION",
    "FAMILY",
    "SUBFAMILY",
    "SUBJECT_ID",
    "SPECIES",
)


def load_default_species_fhir(path_value: str) -> dict[str, Any]:
    path = Path(str(path_value or "").strip()).expanduser()
    if not path.exists():
        return {"system": "http://hl7.org/fhir/target-species", "codes": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"system": "http://hl7.org/fhir/target-species", "codes": {}}
    if not isinstance(data, dict):
        return {"system": "http://hl7.org/fhir/target-species", "codes": {}}
    codes = data.get("codes", {})
    if not isinstance(codes, dict):
        codes = {}
    return {
        "system": str(data.get("system", "http://hl7.org/fhir/target-species")),
        "codes": {str(code).strip(): str(display).strip() for code, display in codes.items() if str(code).strip()},
    }


def default_tenant_config_payload(settings: ServiceSettings) -> dict[str, Any]:
    return {
        "schemaConfig": {
            "headerRowIndex": 1,
            "fieldMap": dict(DEFAULT_SCHEMA_FIELD_MAP),
            "fieldDefaults": {},
            "speciesContains": [],
            "excludedSectionFamilies": [],
            "ownerPublicRules": {
                "enabled": False,
                "containsAny": ["ayuntamiento", "cabildo", "diputacion"],
                "excludeContainsAny": ["S.L.", "S.A."],
                "publicIdPrefixes": ["P", "Q", "S"],
                "identifierRegex": "^(?:[A-Z]\\d{7}[A-Z0-9]|\\d{8}[A-Z])$",
                "relationship": "organization-owner",
            },
            "loincBySectionFamily": {},
            "encounterClassBySectionFamily": {},
            "encounterServiceTypeBySectionFamily": {},
        },
        "speciesFhir": load_default_species_fhir(settings.default_species_fhir_file),
        "speciesLocalToFhirCode": {},
        "runtimeDefaults": {
            "language": "es-ES",
            "dataUse": "secondary",
            "subjectKind": "animal",
            "subjectDidPrefix": settings.default_subject_did_prefix,
            "issuerDid": settings.default_issuer_did,
            "audienceDid": settings.default_audience_did,
            "includeFields": list(DEFAULT_INCLUDE_FIELDS),
        },
    }
