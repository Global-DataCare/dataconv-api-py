# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
from typing import Any
import uuid

from .ai.base import CodingAssistant
from .fhir_claims import (
    AnimalClaim,
    CompositionClaim,
    CompositionClaims,
    DocumentReferenceClaim,
    DocumentReferenceClaims,
    EncounterClaim,
    EncounterClaims,
    OperationOutcomeClaim,
    OperationOutcomeClaims,
    PatientClaim,
    PatientClaims,
    RelatedPersonClaim,
    RelatedPersonClaims,
)
from .models import (
    AdapterContext,
    CanonicalRecord,
    didcomm_plaintext_message,
    jsonapi_resource_entry,
    stable_uuid,
)


DEFAULT_DOCUMENT_CATEGORY_BY_COMPOSITION_SECTION: dict[str, str] = {
    "immunizations": "11369-6",
    "laboratory": "26436-6",
    "imaging": "18748-4",
    "encounters": "11488-4",
    "medications": "56445-0",
    "general": "47045-0",
}

DEFAULT_COMPOSITION_TYPE_BY_SECTION: dict[str, str] = {
    "immunizations": "11369-6",
    "laboratory": "30954-2",
    "imaging": "18726-0",
    "encounters": "34109-9",
    "medications": "10160-0",
    "general": "11503-0",
}

ENCOUNTER_CLASS_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
DEFAULT_ENCOUNTER_CLASS_CODE = "AMB"


def _default_document_category_code(record: CanonicalRecord) -> str:
    text = f"{record.family} {record.subfamily} {record.concept}".lower()
    if "anestes" in text:
        return "11485-0"
    return DEFAULT_DOCUMENT_CATEGORY_BY_COMPOSITION_SECTION.get(record.composition_section, "47045-0")


def _default_composition_type_code(section: str) -> str:
    return DEFAULT_COMPOSITION_TYPE_BY_SECTION.get(section, "47045-0")


def _loinc_claim_value(code: str) -> str:
    code_text = str(code or "").strip()
    return f"http://loinc.org|{code_text}" if code_text else ""


def _urn_uuid(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    if token.startswith("urn:uuid:"):
        return token
    return f"urn:uuid:{token}"


def _owner_public_urn(*, jurisdiction: str, owner_public_hash: str) -> str:
    hash_token = str(owner_public_hash or "").strip()
    if not hash_token:
        return ""
    if hash_token.startswith("urn:"):
        return hash_token
    country = str(jurisdiction or "").strip().upper() or "ES"
    return f"urn:cds:{country}:v1:organization:multibase:{hash_token}"


def _mapping_value_for_record(context: AdapterContext, key_name: str, record: CanonicalRecord) -> str:
    schema = context.schema_config if isinstance(context.schema_config, dict) else {}
    raw_mapping = schema.get(key_name, {})
    if not isinstance(raw_mapping, dict):
        return ""

    section = str(record.section or "").strip().lower()
    family = str(record.family or "").strip().lower()
    candidates = (
        f"{section}:{family}",
        f"{section}:*",
        f"*:{family}",
        "*:*",
    )
    for key in candidates:
        if key in raw_mapping:
            return str(raw_mapping.get(key, "")).strip()
    return ""


def _should_include_narrative_text(context: AdapterContext) -> bool:
    mode = str(getattr(context, "data_use", "individual") or "individual").strip().lower()
    return mode == "individual"


@dataclass(frozen=True)
class PipelineResult:
    composition_message: dict[str, Any]
    summary: dict[str, Any]


def _to_xhtml_table(attributes: dict[str, str]) -> str:
    keys = list(attributes.keys())
    values = [attributes.get(k, "") for k in keys]

    header_cells = "".join(f"<th>{escape(str(key))}</th>" for key in keys)
    value_cells = "".join(f"<td>{escape(str(value))}</td>" for value in values)

    return (
        '<div xmlns="http://www.w3.org/1999/xhtml">'
        "<table>"
        f"<tr>{header_cells}</tr>"
        f"<tr>{value_cells}</tr>"
        "</table>"
        "</div>"
    )


def _doc_claims(
    record: CanonicalRecord,
    context: AdapterContext,
    coding_assistant: CodingAssistant,
) -> tuple[str, DocumentReferenceClaims]:
    document_id = stable_uuid(
        context.manufacturer,
        context.tenant_id,
        record.subject_id,
        record.source_id,
        record.timestamp,
        record.family,
        record.subfamily,
    )

    category_code = record.document_category_code or _default_document_category_code(record)
    suggestions = coding_assistant.suggest_codes(record)

    claims: DocumentReferenceClaims = {
        DocumentReferenceClaim.IDENTIFIER: document_id,
        DocumentReferenceClaim.SUBJECT: record.subject_id,
        DocumentReferenceClaim.AUTHOR: "",
        DocumentReferenceClaim.DATE: record.timestamp or datetime.now(timezone.utc).isoformat(),
        DocumentReferenceClaim.TYPE: record.document_type_code,
        DocumentReferenceClaim.CATEGORY: _loinc_claim_value(category_code),
        DocumentReferenceClaim.DESCRIPTION: record.concept or record.subfamily or record.family,
        DocumentReferenceClaim.LANGUAGE: context.language,
    }
    if _should_include_narrative_text(context):
        # Custom claim: not in common-utils yet, but compatible with claims-first storage.
        claims[DocumentReferenceClaim.TEXT] = _to_xhtml_table(record.attributes)

    if suggestions:
        top = suggestions[0]
        claims[DocumentReferenceClaim.EVENT_CODE] = f"{top.system}|{top.code}"
        claims[DocumentReferenceClaim.MODALITY] = f"{top.display}|confidence:{top.confidence:.2f}"

    return document_id, claims


def _composition_claims(
    context: AdapterContext,
    subject: str,
    section: str,
    composition_type_code: str,
    entry_resource_ids: list[str],
) -> CompositionClaims:
    ordered_entry_ids: list[str] = []
    seen_entry_ids: set[str] = set()
    for raw_id in entry_resource_ids:
        resource_id = str(raw_id or "").strip()
        if not resource_id or resource_id in seen_entry_ids:
            continue
        seen_entry_ids.add(resource_id)
        ordered_entry_ids.append(resource_id)
    stable_entry_ids = sorted(ordered_entry_ids)
    identifier = stable_uuid(context.manufacturer, context.tenant_id, subject, section, *stable_entry_ids)
    entries = ",".join(_urn_uuid(resource_id) for resource_id in ordered_entry_ids)
    timestamp = datetime.now(timezone.utc).isoformat()
    composition_loinc = _loinc_claim_value(composition_type_code or _default_composition_type_code(section))

    claims: CompositionClaims = {
        CompositionClaim.IDENTIFIER: identifier,
        CompositionClaim.SUBJECT: subject,
        CompositionClaim.SECTION: composition_loinc,
        CompositionClaim.AUTHOR: "",
        CompositionClaim.DATE: timestamp,
        CompositionClaim.TYPE: composition_loinc,
        CompositionClaim.TITLE: f"{section} index",
        CompositionClaim.ENTRY: entries,
    }
    return claims


def _doc_resource(document_id: str, claims: DocumentReferenceClaims) -> dict[str, Any]:
    return {
        "resourceType": "DocumentReference",
        "id": document_id,
        "meta": {
            "claims": claims,
        },
    }


def _encounter_claims(
    *,
    context: AdapterContext,
    record: CanonicalRecord,
) -> tuple[str, EncounterClaims]:
    encounter_id = stable_uuid(
        context.manufacturer,
        context.tenant_id,
        record.subject_id,
        "encounter",
        record.source_id,
        record.timestamp,
    )
    encounter_class = _mapping_value_for_record(context, "encounterClassBySectionFamily", record)
    encounter_service_type = _mapping_value_for_record(context, "encounterServiceTypeBySectionFamily", record)
    if encounter_class and "|" not in encounter_class:
        encounter_class = f"{ENCOUNTER_CLASS_SYSTEM}|{encounter_class}"
    if not encounter_class:
        encounter_class = f"{ENCOUNTER_CLASS_SYSTEM}|{DEFAULT_ENCOUNTER_CLASS_CODE}"
    claims: EncounterClaims = {
        EncounterClaim.IDENTIFIER: encounter_id,
        EncounterClaim.SUBJECT: record.subject_id,
        EncounterClaim.DATE: record.timestamp or datetime.now(timezone.utc).isoformat(),
        EncounterClaim.STATUS: "finished",
        EncounterClaim.CLASS: encounter_class,
    }
    if encounter_service_type:
        claims[EncounterClaim.SERVICE_TYPE] = encounter_service_type
    return encounter_id, claims


def _encounter_resource(encounter_id: str, claims: EncounterClaims) -> dict[str, Any]:
    return {
        "resourceType": "Encounter",
        "id": encounter_id,
        "meta": {
            "claims": claims,
        },
    }


def _related_person_claims(
    *,
    context: AdapterContext,
    subject: str,
    owner_public_hash: str,
    owner_public_name: str,
    relationship: str,
) -> tuple[str, RelatedPersonClaims]:
    related_person_id = stable_uuid(
        context.manufacturer,
        context.tenant_id,
        subject,
        "related-person",
        owner_public_hash,
    )
    claims: RelatedPersonClaims = {
        RelatedPersonClaim.IDENTIFIER: _owner_public_urn(
            jurisdiction=context.jurisdiction,
            owner_public_hash=owner_public_hash,
        ),
        RelatedPersonClaim.PATIENT: subject,
        RelatedPersonClaim.RELATIONSHIP: relationship or "organization-owner",
        RelatedPersonClaim.ACTIVE: "true",
    }
    if owner_public_name:
        claims[RelatedPersonClaim.NAME] = owner_public_name
    return related_person_id, claims


def _related_person_resource(related_person_id: str, claims: RelatedPersonClaims) -> dict[str, Any]:
    return {
        "resourceType": "RelatedPerson",
        "id": related_person_id,
        "meta": {
            "claims": claims,
        },
    }


def _patient_claims(
    *,
    context: AdapterContext,
    record: CanonicalRecord,
    patient_link_identifiers: list[str] | None = None,
) -> tuple[str, PatientClaims]:
    patient_id = stable_uuid(
        context.manufacturer,
        context.tenant_id,
        record.subject_id,
        "patient",
    )
    claims: PatientClaims = {
        PatientClaim.IDENTIFIER: record.subject_id,
        PatientClaim.ACTIVE: "true",
        PatientClaim.LANGUAGE: context.language,
    }
    links = sorted({value.strip() for value in (patient_link_identifiers or []) if value and value.strip()})
    if links:
        claims[PatientClaim.LINK] = ",".join(links)
    species_code = str(record.species_fhir_code or "").strip()
    if species_code:
        claims[AnimalClaim.SPECIES] = f"{context.fhir_species_system}|{species_code}"
    breed_code = str(record.animal_breed_code or "").strip()
    if breed_code:
        claims[AnimalClaim.BREED] = breed_code
    gender_status_code = str(record.animal_gender_status_code or "").strip()
    if gender_status_code:
        claims[AnimalClaim.GENDER_STATUS] = gender_status_code
    return patient_id, claims


def _patient_resource(
    patient_id: str,
    claims: PatientClaims,
    contained: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "resourceType": "Patient",
        "id": patient_id,
        "meta": {
            "claims": claims,
        },
        "contained": contained,
    }


def _composition_resource(claims: CompositionClaims) -> dict[str, Any]:
    return {
        "resourceType": "Composition",
        "id": claims[CompositionClaim.IDENTIFIER],
        "meta": {
            "claims": claims,
        },
    }


def _operation_outcome_entries(
    *,
    context: AdapterContext,
    row_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for issue in row_issues:
        if not isinstance(issue, dict):
            continue
        row_number = int(issue.get("rowNumber") or 0)
        section_family = str(issue.get("sectionFamily") or issue.get("compositionSection") or "").strip()
        code = str(issue.get("code") or "processing").strip() or "processing"
        diagnostics = str(issue.get("diagnostics") or "").strip()
        if not diagnostics:
            diagnostics = "Preconversion warning."
        issue_id = stable_uuid(
            context.manufacturer,
            context.tenant_id,
            "operation-outcome",
            str(row_number),
            section_family,
            code,
            diagnostics,
        )
        outcome_resource: dict[str, Any] = {
            "resourceType": "OperationOutcome",
            "id": issue_id,
            "issue": [
                {
                    "severity": "warning",
                    "code": "processing",
                    "details": {
                        "text": "Row skipped during preconversion.",
                    },
                    "diagnostics": diagnostics,
                }
            ],
        }
        outcome_claims: OperationOutcomeClaims = {
            OperationOutcomeClaim.CONTEXT: "org.hl7.fhir.api",
            OperationOutcomeClaim.TYPE: "OperationOutcome:PreconversionRowIssue",
            OperationOutcomeClaim.ROW_NUMBER: str(row_number),
            OperationOutcomeClaim.SECTION_FAMILY: section_family,
            OperationOutcomeClaim.ISSUE_CODE: code,
        }
        resource: dict[str, Any] = {
            **outcome_resource,
            "meta": {
                "claims": outcome_claims,
            },
        }
        entries.append(
            {
                "resource": resource,
                "response": {
                    "status": "422",
                    "outcome": outcome_resource,
                },
            }
        )
    return entries


def _thid(prefix: str) -> str:
    raw = f"{prefix}|{uuid.uuid4()}"
    digest = sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def run_pipeline(
    records: list[CanonicalRecord],
    context: AdapterContext,
    coding_assistant: CodingAssistant,
    row_issues: list[dict[str, Any]] | None = None,
) -> PipelineResult:
    document_entries_count = 0
    encounter_entries_count = 0
    related_person_entries_count = 0
    patient_entries_count = 0
    composition_entries_count = 0
    grouped_doc_resources: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    grouped_encounter_resources: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    grouped_related_resources: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    grouped_patient_link_identifiers: dict[str, set[str]] = defaultdict(set)
    grouped_composition_codes: dict[tuple[str, str], str] = {}
    families: dict[str, int] = defaultdict(int)
    sections: dict[str, int] = defaultdict(int)
    subject_sections: dict[str, set[str]] = defaultdict(set)
    subjects: set[str] = set()
    all_related_person_ids: set[str] = set()
    latest_record_by_subject: dict[str, CanonicalRecord] = {}

    for record in records:
        doc_id, doc_claims = _doc_claims(record, context, coding_assistant)
        document_entries_count += 1
        key = (record.subject_id, record.composition_section)
        grouped_doc_resources[key][doc_id] = _doc_resource(doc_id, doc_claims)

        encounter_id, encounter_claims = _encounter_claims(context=context, record=record)
        grouped_encounter_resources[key][encounter_id] = _encounter_resource(encounter_id, encounter_claims)
        encounter_entries_count += 1

        if record.owner_public_hash:
            owner_identifier = _owner_public_urn(
                jurisdiction=context.jurisdiction,
                owner_public_hash=record.owner_public_hash,
            )
            related_person_id, related_person_claims = _related_person_claims(
                context=context,
                subject=record.subject_id,
                owner_public_hash=record.owner_public_hash,
                owner_public_name=record.owner_public_name,
                relationship=record.owner_public_relationship,
            )
            grouped_related_resources[record.subject_id][related_person_id] = _related_person_resource(
                related_person_id,
                related_person_claims,
            )
            if owner_identifier:
                grouped_patient_link_identifiers[record.subject_id].add(owner_identifier)
            all_related_person_ids.add(related_person_id)
        if key not in grouped_composition_codes and record.composition_type_code:
            grouped_composition_codes[key] = record.composition_type_code
        families[record.family] += 1
        sections[f"{record.section}:{record.family}"] += 1
        subject_sections[record.subject_id].add(record.composition_section)
        subjects.add(record.subject_id)
        latest = latest_record_by_subject.get(record.subject_id)
        if latest is None or str(record.timestamp or "") >= str(latest.timestamp or ""):
            latest_record_by_subject[record.subject_id] = record

    related_person_entries_count = len(all_related_person_ids)

    patient_entries: list[dict[str, Any]] = []
    for subject in sorted(subjects):
        contained_resources: list[dict[str, Any]] = []
        related_ids = sorted(grouped_related_resources[subject].keys())

        for section in sorted(subject_sections[subject]):
            key = (subject, section)
            doc_resources_map = grouped_doc_resources[key]
            encounter_resources_map = grouped_encounter_resources[key]
            doc_ids = sorted(doc_resources_map.keys())
            encounter_ids = sorted(encounter_resources_map.keys())
            entry_ids = encounter_ids + doc_ids
            claims = _composition_claims(
                context=context,
                subject=subject,
                section=section,
                composition_type_code=grouped_composition_codes.get(key, ""),
                entry_resource_ids=entry_ids,
            )
            contained_resources.append(_composition_resource(claims=claims))
            composition_entries_count += 1

            for resource_id in encounter_ids:
                contained_resources.append(encounter_resources_map[resource_id])
            for resource_id in doc_ids:
                contained_resources.append(doc_resources_map[resource_id])

        for related_id in related_ids:
            contained_resources.append(grouped_related_resources[subject][related_id])

        patient_record = latest_record_by_subject[subject]
        patient_id, patient_claims = _patient_claims(
            context=context,
            record=patient_record,
            patient_link_identifiers=sorted(grouped_patient_link_identifiers[subject]),
        )
        patient_entries.append(
            jsonapi_resource_entry(
                _patient_resource(
                    patient_id=patient_id,
                    claims=patient_claims,
                    contained=contained_resources,
                )
            )
        )
        patient_entries_count += 1

    outcome_entries = _operation_outcome_entries(
        context=context,
        row_issues=[item for item in (row_issues or []) if isinstance(item, dict)],
    )
    bundle_entries = patient_entries + outcome_entries

    composition_message = didcomm_plaintext_message(
        thid=_thid("patient"),
        issuer_did=context.issuer_did,
        audience_did=context.audience_did,
        entries=bundle_entries,
    )

    summary = {
        "manufacturer": context.manufacturer,
        "tenantId": context.tenant_id,
        "jurisdiction": context.jurisdiction,
        "sector": context.sector,
        "recordsTotal": len(records),
        "subjectsTotal": len(subjects),
        "documentReferenceEntries": document_entries_count,
        "encounterEntries": encounter_entries_count,
        "relatedPersonEntries": related_person_entries_count,
        "patientEntries": patient_entries_count,
        "compositionEntries": composition_entries_count,
        "operationOutcomeEntries": len(outcome_entries),
        "families": dict(sorted(families.items(), key=lambda item: (-item[1], item[0]))),
        "sections": dict(sorted(sections.items(), key=lambda item: (-item[1], item[0]))),
    }

    return PipelineResult(
        composition_message=composition_message,
        summary=summary,
    )
