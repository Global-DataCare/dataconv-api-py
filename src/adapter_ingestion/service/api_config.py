# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from ..manufacturers.xlsx_common import normalize_token, read_tabular_row_cells

RESERVED_API_CONFIG_SOFTWARE_ID = "api-config"
API_CONFIG_MARKER = "API-CONFIG"

_FIELD_NAME_ALIASES = {
    "section": "section",
    "family": "family",
    "subfamily": "subfamily",
    "concept": "concept",
    "subjectid": "subject_id",
    "subject-id": "subject_id",
    "subject_id": "subject_id",
    "subjectanimalspecies": "species",
    "subject_animal_species": "species",
    "subjectanimalbreeds": "breed",
    "subject_animal_breeds": "breed",
    "subjectanimalgenderstatus": "genderStatus",
    "subject_animal_genderstatus": "genderStatus",
    "subjectbirthyear": "birthyear",
    "subject_birthyear": "birthyear",
    "subjectbirthsex": "birthsex",
    "subject_birthsex": "birthsex",
    "owner": "owner",
    "ownerid": "ownerId",
    "species": "species",
    "especie": "species",
    "especies": "species",
    "personalid": "personal_id",
    "personal-id": "personal_id",
    "personal_id": "personal_id",
    "breed": "breed",
    "genderstatus": "genderStatus",
    "sourceid": "sourceId",
    "date": "date",
    "time": "time",
}


def is_reserved_api_config_software_id(value: str) -> bool:
    return str(value or "").strip().lower() == RESERVED_API_CONFIG_SOFTWARE_ID


def deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, value in (base or {}).items():
        merged[key] = dict(value) if isinstance(value, dict) else value
    for key, value in (override or {}).items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = deep_merge_dicts(current, value)
        else:
            merged[key] = value
    return merged


def _canonical_field_name(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    alias_key = re.sub(r"[^a-z0-9]+", "", normalize_token(raw))
    if alias_key in _FIELD_NAME_ALIASES:
        return _FIELD_NAME_ALIASES[alias_key]
    return raw


def _marker_runtime_defaults(marker: str) -> dict[str, Any]:
    text = str(marker or "").strip()
    if not text:
        return {}
    tokens = [tok.strip() for tok in re.split(r"[;:]", text) if tok.strip()]
    if not tokens or normalize_token(tokens[0]) != normalize_token(API_CONFIG_MARKER):
        return {}

    runtime_defaults: dict[str, Any] = {}
    idx = 1
    while idx < len(tokens):
        token = tokens[idx]
        value = ""
        if "=" in token:
            key, value = token.split("=", 1)
            idx += 1
        elif idx + 1 < len(tokens):
            key = token
            value = tokens[idx + 1]
            idx += 2
        else:
            idx += 1
            continue
        normalized_key = normalize_token(key)
        normalized_value = str(value or "").strip()
        if not normalized_value:
            continue
        if normalized_key == "language":
            runtime_defaults["language"] = normalized_value
        elif normalized_key in {"software-id", "software_id", "softwareid"}:
            runtime_defaults["softwareId"] = normalized_value
        elif normalized_key == "subjectkind":
            runtime_defaults["subjectKind"] = normalized_value
        elif normalized_key == "subjectdidprefix":
            runtime_defaults["subjectDidPrefix"] = normalized_value
        elif normalized_key == "issuerdid":
            runtime_defaults["issuerDid"] = normalized_value
        elif normalized_key == "audiencedid":
            runtime_defaults["audienceDid"] = normalized_value
        elif normalized_key == "datause":
            runtime_defaults["dataUse"] = normalized_value
        elif normalized_key == "logcomposition":
            runtime_defaults["logComposition"] = normalized_value.lower() in {"1", "true", "yes", "on"}
    return runtime_defaults


def extract_embedded_api_config(file_path: Path) -> dict[str, Any] | None:
    rows = read_tabular_row_cells(file_path, max_rows=3)
    if len(rows) < 3:
        return None

    marker = str(rows[0].get(0, "")).strip()
    runtime_defaults = _marker_runtime_defaults(marker)
    marker_head = re.split(r"[;:]", marker, maxsplit=1)[0].strip()
    if normalize_token(marker_head) != normalize_token(API_CONFIG_MARKER):
        return None

    config_row = rows[1]
    source_header_row = rows[2]
    field_map: dict[str, str] = {}
    for column_index, raw_field_name in sorted(config_row.items()):
        field_name = _canonical_field_name(raw_field_name)
        source_header = str(source_header_row.get(column_index, "")).strip()
        if not field_name or not source_header:
            continue
        field_map[field_name] = source_header

    extracted: dict[str, Any] = {
        "schemaConfig": {
            "headerRowIndex": 3,
            "fieldMap": field_map,
        }
    }
    if runtime_defaults:
        extracted["runtimeDefaults"] = runtime_defaults
    return extracted
