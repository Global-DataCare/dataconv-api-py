# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import re
import uuid

from .base import ManufacturerAdapter
from .xlsx_common import (
    composition_section,
    normalize_token,
    parse_fhir_datetime,
    read_csv_rows,
    read_xlsx_rows,
    resolve_species_local_and_code,
    slug,
)
from ..models import AdapterContext, CanonicalRecord, stable_id


_BASE58BTC_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BASE58BTC_CHARS = set(_BASE58BTC_ALPHABET)
_DEFAULT_OWNER_PUBLIC_ID_PREFIXES = ("P", "Q", "S")
_DEFAULT_OWNER_PUBLIC_CONTAINS = (
    "ayuntamiento",
    "cabildo",
    "diputacion",
    "ministerio",
    "consejeria",
    "gobierno",
    "comunidad autonoma",
    "administracion publica",
)
_DEFAULT_OWNER_EXCLUDE_CONTAINS = (
    " s l ",
    " s a ",
    "slu",
    "sau",
    "slp",
    "cooperativa",
    "empresa",
    "mercantil",
)
_DEFAULT_OWNER_IDENTIFIER_REGEX = r"^(?:[A-Z]\d{7}[A-Z0-9]|\d{8}[A-Z])$"


def _is_base58btc_text(text: str) -> bool:
    value = str(text or "").strip()
    return bool(value) and all(char in _BASE58BTC_CHARS for char in value)


def _base58btc_encode(raw: bytes) -> str:
    if not raw:
        return ""
    leading_zeros = 0
    for byte in raw:
        if byte == 0:
            leading_zeros += 1
            continue
        break
    number = int.from_bytes(raw, byteorder="big", signed=False)
    encoded = ""
    while number > 0:
        number, remainder = divmod(number, 58)
        encoded = _BASE58BTC_ALPHABET[remainder] + encoded
    return ("1" * leading_zeros) + (encoded or "")


def _token_to_multibase_sha3(token: str) -> str:
    compact = "".join(str(token or "").strip().split())
    if not compact:
        return ""
    if compact.startswith("z") and _is_base58btc_text(compact[1:]):
        return compact
    digest = hashlib.sha3_256(compact.encode("utf-8")).digest()
    # multihash prefix for SHA3-256: 0x16 + digest length 0x20.
    multihash = bytes((0x16, 0x20)) + digest
    return f"z{_base58btc_encode(multihash)}"


class TabularXlsxAdapter(ManufacturerAdapter):
    name = "tabular"
    source_namespace = "tabular"
    default_header_row_index = 1
    species_fallback_to_source = True
    default_field_map: dict[str, str] = {}
    default_field_defaults: dict[str, str] = {}
    default_species_contains: list[dict[str, str]] = []
    default_loinc_overrides: dict[str, str] = {}

    def __init__(self) -> None:
        self.last_report: dict[str, Any] = {}

    def get_last_report(self) -> dict:
        return dict(self.last_report)

    def _schema(self, context: AdapterContext) -> dict[str, Any]:
        return context.schema_config if isinstance(context.schema_config, dict) else {}

    def _header_row_index(self, schema: dict[str, Any]) -> int:
        raw = schema.get("headerRowIndex", self.default_header_row_index)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return self.default_header_row_index
        return value if value >= 1 else self.default_header_row_index

    def _build_field_map(self, schema: dict[str, Any]) -> dict[str, str]:
        merged = dict(self.default_field_map)
        raw_map = schema.get("fieldMap")
        if isinstance(raw_map, dict):
            for key, value in raw_map.items():
                if str(key).strip():
                    merged[self._canonical_field_name(str(key).strip())] = str(value).strip()
        else:
            # Shorthand form: allow top-level field keys like {"concept": "CONCEPTO"}.
            for key in (
                "section",
                "family",
                "subfamily",
                "concept",
                "subjectId",
                "subject-id",
                "personalId",
                "personal-id",
                "species",
                "breed",
                "genderStatus",
                "owner",
                "ownerId",
                "sourceId",
                "date",
                "time",
            ):
                if key in schema and str(schema.get(key, "")).strip():
                    merged[self._canonical_field_name(key)] = str(schema.get(key)).strip()
        return merged

    def _canonical_field_name(self, field_name: str) -> str:
        key = str(field_name or "").strip()
        if key == "subject-id":
            return "subjectId"
        if key == "personal-id":
            return "personalId"
        return key

    def _build_field_defaults(self, schema: dict[str, Any]) -> dict[str, str]:
        merged = dict(self.default_field_defaults)
        raw_defaults = schema.get("fieldDefaults")
        if isinstance(raw_defaults, dict):
            for key, value in raw_defaults.items():
                if str(key).strip():
                    merged[str(key).strip()] = str(value).strip()
        return merged

    def _normalized_owner_search_text(self, text: str) -> str:
        normalized = normalize_token(text)
        compact = re.sub(r"[^a-z0-9]+", " ", normalized)
        return f" {compact.strip()} "

    def _build_owner_public_rules(self, schema: dict[str, Any]) -> dict[str, Any]:
        raw_rules = schema.get("ownerPublicRules", {})
        if not isinstance(raw_rules, dict):
            raw_rules = {}

        contains_any = raw_rules.get("containsAny", _DEFAULT_OWNER_PUBLIC_CONTAINS)
        if not isinstance(contains_any, list):
            contains_any = list(_DEFAULT_OWNER_PUBLIC_CONTAINS)
        exclude_contains_any = raw_rules.get("excludeContainsAny", _DEFAULT_OWNER_EXCLUDE_CONTAINS)
        if not isinstance(exclude_contains_any, list):
            exclude_contains_any = list(_DEFAULT_OWNER_EXCLUDE_CONTAINS)
        public_prefixes = raw_rules.get("publicIdPrefixes", _DEFAULT_OWNER_PUBLIC_ID_PREFIXES)
        if not isinstance(public_prefixes, list):
            public_prefixes = list(_DEFAULT_OWNER_PUBLIC_ID_PREFIXES)

        contains_tokens = [
            self._normalized_owner_search_text(str(item))
            for item in contains_any
            if str(item or "").strip()
        ]
        exclude_tokens = [
            self._normalized_owner_search_text(str(item))
            for item in exclude_contains_any
            if str(item or "").strip()
        ]
        prefixes = [str(item or "").strip().upper()[:1] for item in public_prefixes if str(item or "").strip()]

        regex_text = str(raw_rules.get("identifierRegex", _DEFAULT_OWNER_IDENTIFIER_REGEX)).strip()
        try:
            identifier_regex = re.compile(regex_text, re.IGNORECASE)
        except re.error:
            identifier_regex = re.compile(_DEFAULT_OWNER_IDENTIFIER_REGEX, re.IGNORECASE)

        return {
            "enabled": bool(raw_rules.get("enabled", False)),
            "containsAny": contains_tokens,
            "excludeContainsAny": exclude_tokens,
            "publicIdPrefixes": prefixes,
            "identifierRegex": identifier_regex,
            "relationship": str(raw_rules.get("relationship", "organization-owner")).strip()
            or "organization-owner",
        }

    def _extract_owner_identifier(
        self,
        *,
        owner_text: str,
        owner_id_text: str,
        identifier_regex: re.Pattern,
    ) -> str:
        candidates = [owner_id_text, owner_text]
        for candidate in candidates:
            text = str(candidate or "").strip().upper()
            if not text:
                continue
            tokens = re.findall(r"[A-Z0-9]+", text)
            for token in tokens:
                compact = re.sub(r"[^A-Z0-9]+", "", token)
                if compact and identifier_regex.match(compact):
                    return compact
        return ""

    def _contains_any_token(self, search_text: str, tokens: list[str]) -> bool:
        for token in tokens:
            token_text = str(token or "").strip()
            if token_text and token_text in search_text:
                return True
        return False

    def _resolve_public_owner(
        self,
        *,
        owner_text: str,
        owner_id_text: str,
        owner_rules: dict[str, Any],
    ) -> tuple[str, str]:
        if not owner_rules.get("enabled"):
            return ("", "")

        owner_name = str(owner_text or "").strip()
        search_text = self._normalized_owner_search_text(owner_name)
        exclude_tokens = owner_rules.get("excludeContainsAny", [])
        if isinstance(exclude_tokens, list) and self._contains_any_token(search_text, exclude_tokens):
            return ("", "")

        identifier_regex = owner_rules.get("identifierRegex")
        if not isinstance(identifier_regex, re.Pattern):
            identifier_regex = re.compile(_DEFAULT_OWNER_IDENTIFIER_REGEX, re.IGNORECASE)
        owner_identifier = self._extract_owner_identifier(
            owner_text=owner_name,
            owner_id_text=str(owner_id_text or "").strip(),
            identifier_regex=identifier_regex,
        )
        if not owner_identifier:
            return ("", "")

        public_prefixes = owner_rules.get("publicIdPrefixes", [])
        if isinstance(public_prefixes, list) and public_prefixes:
            if owner_identifier[0].upper() not in {prefix for prefix in public_prefixes if prefix}:
                return ("", "")

        contains_tokens = owner_rules.get("containsAny", [])
        if isinstance(contains_tokens, list) and contains_tokens:
            if not self._contains_any_token(search_text, contains_tokens):
                return ("", "")

        return (_token_to_multibase_sha3(owner_identifier), owner_name)

    def _build_species_contains(self, schema: dict[str, Any]) -> list[dict[str, str]]:
        contains = list(self.default_species_contains)
        raw_rules = schema.get("speciesContains", [])
        if isinstance(raw_rules, list):
            for item in raw_rules:
                if not isinstance(item, dict):
                    continue
                contains_text = str(item.get("contains", "")).strip()
                if not contains_text:
                    continue
                contains.append(
                    {
                        "contains": contains_text,
                        "value": str(
                            item.get("value")
                            or item.get("local")
                            or item.get("label")
                            or contains_text
                        ).strip(),
                    }
                )
        return contains

    def _parse_loinc_code(self, raw_value: Any) -> str:
        value = str(raw_value or "").strip()
        if not value:
            return ""
        if "|" in value:
            value = value.rsplit("|", 1)[-1].strip()
        if value.lower().startswith("http://loinc.org/"):
            value = value.rsplit("/", 1)[-1].strip()
        return value

    def _normalize_section_family_key(self, key_text: str) -> str:
        text = str(key_text or "").strip()
        if ":" not in text:
            return ""
        section, family = text.split(":", 1)
        return f"{normalize_token(section)}:{normalize_token(family)}"

    def _build_loinc_overrides(
        self,
        raw_overrides: Any,
        default_overrides: dict[str, str],
    ) -> dict[str, str]:
        merged: dict[str, str] = {
            self._normalize_section_family_key(key): self._parse_loinc_code(value)
            for key, value in default_overrides.items()
            if self._normalize_section_family_key(key) and self._parse_loinc_code(value)
        }
        if not isinstance(raw_overrides, dict):
            return merged
        for key, value in raw_overrides.items():
            normalized_key = self._normalize_section_family_key(str(key))
            code = self._parse_loinc_code(value)
            if normalized_key and code:
                merged[normalized_key] = code
        return merged

    def _build_allowed_sections(self, schema: dict[str, Any]) -> set[str]:
        raw = schema.get("allowedSections", [])
        if not isinstance(raw, list):
            return set()
        return {
            normalize_token(item)
            for item in raw
            if str(item or "").strip()
        }

    def _build_excluded_sections(self, schema: dict[str, Any]) -> set[str]:
        raw = schema.get("excludedSections", [])
        if not isinstance(raw, list):
            return set()
        return {
            normalize_token(item)
            for item in raw
            if str(item or "").strip()
        }

    def _build_excluded_section_families(self, schema: dict[str, Any]) -> set[str]:
        raw = schema.get("excludedSectionFamilies", [])
        if not isinstance(raw, list):
            return set()
        normalized: set[str] = set()
        for item in raw:
            key = self._normalize_section_family_key(str(item or ""))
            if key:
                normalized.add(key)
        return normalized

    def _is_section_family_excluded(
        self,
        *,
        section: str,
        family: str,
        excluded_section_families: set[str],
    ) -> bool:
        if not excluded_section_families:
            return False
        section_normalized = normalize_token(section)
        family_normalized = normalize_token(family)
        if not section_normalized or not family_normalized:
            return False
        if f"{section_normalized}:{family_normalized}" in excluded_section_families:
            return True
        if f"{section_normalized}:*" in excluded_section_families:
            return True
        if f"*:{family_normalized}" in excluded_section_families:
            return True
        return "*:*" in excluded_section_families

    def _resolve_loinc_code_for_record(
        self,
        section: str,
        family: str,
        overrides: dict[str, str],
    ) -> str:
        section_normalized = normalize_token(section)
        family_normalized = normalize_token(family)
        exact_key = f"{section_normalized}:{family_normalized}"
        if exact_key in overrides:
            return overrides[exact_key]
        wildcard_key = f"{section_normalized}:*"
        if wildcard_key in overrides:
            return overrides[wildcard_key]
        return ""

    def _field_value(
        self,
        row: dict[str, str],
        field_map: dict[str, str],
        field_defaults: dict[str, str],
        field_name: str,
    ) -> str:
        source_column = self._source_column(field_map, field_name)
        if source_column:
            value = str(row.get(source_column, "")).strip()
            if value:
                return value
        return str(field_defaults.get(field_name, "")).strip()

    def _source_column(
        self,
        field_map: dict[str, str],
        field_name: str,
    ) -> str:
        return str(field_map.get(self._canonical_field_name(field_name), "")).strip()

    def _build_attributes(self, row: dict[str, str], include_fields: tuple[str, ...]) -> dict[str, str]:
        non_empty = {k: str(v).strip() for k, v in row.items() if str(v).strip()}
        tokens = [str(token).strip() for token in include_fields if str(token).strip()]
        if not tokens:
            return dict(non_empty)

        by_upper: dict[str, tuple[str, str]] = {}
        for key, value in non_empty.items():
            upper = key.strip().upper()
            if upper and upper not in by_upper:
                by_upper[upper] = (key, value)

        selected: dict[str, str] = {}
        for token in tokens:
            parts = [part.strip().upper() for part in token.split("+") if part.strip()]
            if not parts:
                continue
            if len(parts) == 1:
                entry = by_upper.get(parts[0])
                if entry:
                    selected[entry[0]] = entry[1]
                continue

            joined_values: list[str] = []
            joined_labels: list[str] = []
            for part in parts:
                entry = by_upper.get(part)
                if entry:
                    joined_labels.append(entry[0])
                    joined_values.append(entry[1])
            if joined_values:
                label = "+".join(joined_labels)
                selected[label] = " ".join(joined_values)

        return selected

    def _lookup_species_code(self, context: AdapterContext, raw_species: str) -> str | None:
        raw = (raw_species or "").strip()
        if not raw:
            return None
        if raw in context.fhir_species_catalog:
            return raw
        normalized = normalize_token(raw)
        if normalized in context.fhir_species_catalog:
            return normalized
        # Match by catalog display (configured per clinic), e.g. "Perro" -> code.
        for code, display in context.fhir_species_catalog.items():
            if normalize_token(display) == normalized:
                return str(code).strip()
        lookup_keys = (raw, raw.upper(), normalized)
        for key in lookup_keys:
            if key in context.species_local_to_fhir:
                code = str(context.species_local_to_fhir[key]).strip()
                return code or None
        return None

    def _subject_id(self, context: AdapterContext, subject_token: str, species_code: str | None) -> str | None:
        token_value = (subject_token or "").strip()
        if not token_value:
            return None

        prefix = context.subject_did_prefix.strip().rstrip(":") or "did:web:example.org"
        subject_kind = (context.subject_kind or "animal").strip().lower()
        normalized_token = _token_to_multibase_sha3(token_value)
        if not normalized_token:
            return None
        if subject_kind == "species":
            kind_segment = f"species-{species_code}" if species_code else "species"
        else:
            kind_segment = "animal"
        return f"{prefix}:{kind_segment}:subject:{normalized_token}"

    def _resolve_subject_token(
        self,
        *,
        context: AdapterContext,
        row: dict[str, str],
        field_map: dict[str, str],
        field_defaults: dict[str, str],
    ) -> str:
        subject_token = self._field_value(row, field_map, field_defaults, "subjectId")
        if subject_token:
            return subject_token

        personal_id_column = self._source_column(field_map, "personalId")
        has_personal_id_mapping = bool(personal_id_column or str(field_defaults.get("personalId", "")).strip())
        if not has_personal_id_mapping:
            return ""

        personal_id_value = self._field_value(row, field_map, field_defaults, "personalId")
        resolved_token = ""
        if callable(getattr(context, "personal_id_resolver", None)):
            resolved_token = str(context.personal_id_resolver(personal_id_value)).strip()
        if not resolved_token:
            resolved_token = str(uuid.uuid4())

        subject_column = self._source_column(field_map, "subjectId")
        if subject_column:
            row[subject_column] = resolved_token
        if personal_id_column:
            row[personal_id_column] = resolved_token
        return resolved_token

    def read_records(self, input_path: Path, context: AdapterContext) -> list[CanonicalRecord]:
        suffix = input_path.suffix.lower()
        if suffix not in {".xlsx", ".csv"}:
            raise ValueError(f"{self.name} adapter requires .xlsx or .csv input, received: {input_path.name}")

        schema = self._schema(context)
        header_row_index = self._header_row_index(schema)
        field_map = self._build_field_map(schema)
        field_defaults = self._build_field_defaults(schema)
        owner_public_rules = self._build_owner_public_rules(schema)
        species_contains = self._build_species_contains(schema)
        raw_loinc_overrides: dict[str, str] = {}
        if isinstance(schema.get("documentCategoryLoincBySectionFamily"), dict):
            raw_loinc_overrides.update(schema.get("documentCategoryLoincBySectionFamily"))
        if isinstance(schema.get("compositionTypeLoincBySectionFamily"), dict):
            raw_loinc_overrides.update(schema.get("compositionTypeLoincBySectionFamily"))
        if isinstance(schema.get("loincBySectionFamily"), dict):
            raw_loinc_overrides.update(schema.get("loincBySectionFamily"))
        loinc_overrides = self._build_loinc_overrides(
            raw_loinc_overrides,
            self.default_loinc_overrides,
        )
        allowed_sections = self._build_allowed_sections(schema)
        excluded_sections = self._build_excluded_sections(schema)
        excluded_section_families = self._build_excluded_section_families(schema)
        if suffix == ".csv":
            rows = read_csv_rows(input_path, header_row_index=header_row_index)
        else:
            rows = read_xlsx_rows(input_path, header_row_index=header_row_index)

        records: list[CanonicalRecord] = []
        include_set = {name.strip().upper() for name in context.include_fields if name.strip()}
        species_counts: dict[str, int] = {}
        unmapped_species_counts: dict[str, int] = {}
        invalid_species_code_counts: dict[str, int] = {}
        dropped_without_subject_id = 0
        dropped_by_section_filter = 0
        dropped_by_section_family_filter = 0
        dropped_missing_loinc_mapping = 0
        records_with_public_owner = 0
        missing_loinc_by_section_family: dict[str, int] = {}
        row_issues: list[dict[str, Any]] = []

        for parsed_row in rows:
            row_number = parsed_row.row_number
            row = parsed_row.values

            family = self._field_value(row, field_map, field_defaults, "family")
            if not family:
                continue

            section = self._field_value(row, field_map, field_defaults, "section")
            normalized_section = normalize_token(section)
            if allowed_sections and normalized_section not in allowed_sections:
                dropped_by_section_filter += 1
                continue
            if excluded_sections and normalized_section in excluded_sections:
                dropped_by_section_filter += 1
                continue
            if self._is_section_family_excluded(
                section=section,
                family=family,
                excluded_section_families=excluded_section_families,
            ):
                dropped_by_section_family_filter += 1
                continue
            subfamily = self._field_value(row, field_map, field_defaults, "subfamily")
            concept = self._field_value(row, field_map, field_defaults, "concept")
            subject_token = self._resolve_subject_token(
                context=context,
                row=row,
                field_map=field_map,
                field_defaults=field_defaults,
            )
            owner_text = self._field_value(row, field_map, field_defaults, "owner")
            owner_id_text = self._field_value(row, field_map, field_defaults, "ownerId")
            date_raw = self._field_value(row, field_map, field_defaults, "date")
            time_raw = self._field_value(row, field_map, field_defaults, "time")

            species_source = self._field_value(row, field_map, field_defaults, "species")
            breed_source = self._field_value(row, field_map, field_defaults, "breed")
            gender_status_source = self._field_value(row, field_map, field_defaults, "genderStatus")
            species_raw, species_code_rule = resolve_species_local_and_code(
                species_source,
                contains_rules=species_contains,
                fallback_to_source=self.species_fallback_to_source,
            )

            if species_raw:
                species_counts[species_raw] = species_counts.get(species_raw, 0) + 1

            species_code = species_code_rule or self._lookup_species_code(context, species_raw)
            if species_code and context.fhir_species_catalog and species_code not in context.fhir_species_catalog:
                invalid_species_code_counts[species_code] = invalid_species_code_counts.get(species_code, 0) + 1
                species_code = None
            if species_raw and not species_code:
                unmapped_species_counts[species_raw] = unmapped_species_counts.get(species_raw, 0) + 1

            timestamp = parse_fhir_datetime(date_raw=date_raw, time_raw=time_raw)
            source_id = self._field_value(row, field_map, field_defaults, "sourceId")
            if not source_id:
                source_id = stable_id("src", self.name, str(row_number), concept, family, subfamily)

            subject_id = self._subject_id(context, subject_token=subject_token, species_code=species_code)
            if not subject_id:
                dropped_without_subject_id += 1
                continue

            owner_public_hash, owner_public_name = self._resolve_public_owner(
                owner_text=owner_text,
                owner_id_text=owner_id_text,
                owner_rules=owner_public_rules,
            )
            if owner_public_hash:
                records_with_public_owner += 1

            comp_section = composition_section(section, family)
            loinc_code = self._resolve_loinc_code_for_record(
                section=section,
                family=family,
                overrides=loinc_overrides,
            )
            if not loinc_code:
                dropped_missing_loinc_mapping += 1
                missing_loinc_by_section_family[comp_section] = (
                    missing_loinc_by_section_family.get(comp_section, 0) + 1
                )
                row_issues.append(
                    {
                        "rowNumber": row_number,
                        "code": "missing-loinc-mapping",
                        "section": section,
                        "family": family,
                        "subfamily": subfamily,
                        "concept": concept,
                        "sectionFamily": comp_section,
                        "diagnostics": (
                            "Missing required LOINC mapping for "
                            f"section:family '{comp_section}'."
                        ),
                    }
                )
                continue
            doc_type = (
                f"urn:gdc:{self.source_namespace}:{slug(section)}:{slug(family)}:{slug(subfamily or concept)}"
            )
            attributes = self._build_attributes(row, context.include_fields)
            if species_raw and species_code and "ESPECIE_FHIR_CODE" in include_set:
                attributes["ESPECIE_FHIR_CODE"] = species_code
            if species_raw and species_code and "ESPECIE_FHIR_DISPLAY_EN" in include_set:
                display = context.fhir_species_catalog.get(species_code, "")
                if display:
                    attributes["ESPECIE_FHIR_DISPLAY_EN"] = display

            records.append(
                CanonicalRecord(
                    source_row_number=row_number,
                    source_id=source_id,
                    timestamp=timestamp,
                    subject_id=subject_id,
                    section=section,
                    family=family,
                    subfamily=subfamily,
                    concept=concept,
                    composition_section=comp_section,
                    document_type_code=doc_type,
                    attributes=attributes,
                    species_local=species_raw,
                    species_fhir_code=species_code or "",
                    animal_breed_code=str(breed_source or "").strip(),
                    animal_gender_status_code=str(gender_status_source or "").strip(),
                    document_category_code=loinc_code,
                    composition_type_code=loinc_code,
                    owner_public_hash=owner_public_hash,
                    owner_public_name=owner_public_name,
                    owner_public_relationship=str(owner_public_rules.get("relationship") or "organization-owner"),
                )
            )

        self.last_report = {
            "rowsRead": len(rows),
            "headerRowIndex": header_row_index,
            "recordsAccepted": len(records),
            "recordsDroppedNoSubjectId": dropped_without_subject_id,
            "recordsDroppedSectionFilter": dropped_by_section_filter,
            "recordsDroppedSectionFamilyFilter": dropped_by_section_family_filter,
            "recordsDroppedMissingLoincMapping": dropped_missing_loinc_mapping,
            "recordsWithPublicOwner": records_with_public_owner,
            "missingLoincBySectionFamily": dict(
                sorted(missing_loinc_by_section_family.items(), key=lambda item: (-item[1], item[0]))
            ),
            "rowIssues": row_issues,
            "speciesCounts": dict(
                sorted(species_counts.items(), key=lambda item: (-item[1], item[0]))
            ),
            "unmappedSpeciesCounts": dict(
                sorted(unmapped_species_counts.items(), key=lambda item: (-item[1], item[0]))
            ),
            "invalidSpeciesCodeCounts": dict(
                sorted(invalid_species_code_counts.items(), key=lambda item: (-item[1], item[0]))
            ),
        }

        if context.strict_species_mapping and (unmapped_species_counts or invalid_species_code_counts):
            samples = ", ".join(
                f"{label}({count})"
                for label, count in sorted(
                    unmapped_species_counts.items(), key=lambda item: (-item[1], item[0])
                )[:20]
            )
            invalid_samples = ", ".join(
                f"{code}({count})"
                for code, count in sorted(
                    invalid_species_code_counts.items(), key=lambda item: (-item[1], item[0])
                )[:20]
            )
            detail = ""
            if samples:
                detail += f"Unmapped species values: {samples}. "
            if invalid_samples:
                detail += f"Invalid species codes not found in catalog: {invalid_samples}. "
            raise ValueError(
                "Species mapping is incomplete. "
                f"{detail}Provide --species-local-map-file or run with "
                "--export-species-template/--allow-unmapped-species."
            )
        return records
