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
import re

from gdc_data_utils import (
    ChargeItemClaim,
    DiagnosticReportClaim,
    FHIR_API_CONTEXT,
    InvoiceClaim,
)

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
    RelatedPersonClaim,
    RelatedPersonClaims,
    SubjectClaim,
    SubjectClaims,
    ResearchSubjectClaim,
)
from .models import (
    AdapterContext,
    CanonicalRecord,
    didcomm_plaintext_message,
    jsonapi_resource_entry,
    stable_uuid,
)


ENCOUNTER_CLASS_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
DEFAULT_ENCOUNTER_CLASS_CODE = "AMB"
DEFAULT_UNCODED_VALUE = "default"
DEFAULT_DOCUMENT_CATEGORY_BY_COMPOSITION_SECTION: dict[str, str] = {
    "immunizations": "11369-6",
    "laboratory": "26436-6",
    "imaging": "18748-4",
    "encounters": "11488-4",
    "medications": "56445-0",
}
DEFAULT_COMPOSITION_TYPE_BY_SECTION: dict[str, str] = {
    "immunizations": "11369-6",
    "laboratory": "30954-2",
    "imaging": "18726-0",
    "encounters": "34109-9",
    "medications": "10160-0",
}


def _loinc_claim_value(code: str) -> str:
    code_text = str(code or "").strip()
    return f"http://loinc.org|{code_text}" if code_text else ""


def _sanitize_summary_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.upper() == "SIN DATO":
        return ""
    compact = re.sub(r"[\[\]'\"]+", "", text)
    compact = re.sub(r"\s+", " ", compact).strip(" ,;-")
    return compact


def _claims_have_meaningful_values(
    claims: dict[str, Any],
    *,
    ignored_claim_keys: set[str] | None = None,
) -> bool:
    ignored = {str(key or "").strip() for key in (ignored_claim_keys or set()) if str(key or "").strip()}
    for key, value in (claims or {}).items():
        claim_key = str(key or "").strip()
        if not claim_key or claim_key in ignored:
            continue
        if _sanitize_summary_text(str(value or "")):
            return True
    return False


def _document_description(record: CanonicalRecord) -> str:
    direct = _sanitize_summary_text(record.concept)
    if direct:
        return direct

    candidates = [
        record.species_local,
        record.animal_breed_code,
        record.family if record.family != DEFAULT_UNCODED_VALUE else "",
        record.subfamily if record.subfamily != DEFAULT_UNCODED_VALUE else "",
        record.timestamp.split("T", 1)[0] if "T" in str(record.timestamp or "") else record.timestamp,
    ]
    cleaned = []
    seen: set[str] = set()
    for candidate in candidates:
        value = _sanitize_summary_text(candidate)
        normalized = value.lower()
        if not value or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(value)
    return " | ".join(cleaned) if cleaned else DEFAULT_UNCODED_VALUE


def _is_synthetic_document_type(value: str) -> bool:
    token = str(value or "").strip()
    return token.startswith("urn:gdc:")


def _resolved_document_type(record: CanonicalRecord) -> str:
    token = str(record.document_type_code or "").strip()
    if not token or _is_synthetic_document_type(token):
        return DEFAULT_UNCODED_VALUE
    return token


def _resolved_document_category(record: CanonicalRecord) -> str:
    token = str(record.document_category_code or "").strip()
    if token:
        return _loinc_claim_value(token)
    fallback = DEFAULT_DOCUMENT_CATEGORY_BY_COMPOSITION_SECTION.get(str(record.composition_section or "").strip(), "")
    if fallback:
        return _loinc_claim_value(fallback)
    return DEFAULT_UNCODED_VALUE


def _resolved_composition_type(section: str, composition_type_code: str) -> str:
    token = str(composition_type_code or "").strip()
    if token:
        return _loinc_claim_value(token)
    fallback = DEFAULT_COMPOSITION_TYPE_BY_SECTION.get(str(section or "").strip(), "")
    if fallback:
        return _loinc_claim_value(fallback)
    return DEFAULT_UNCODED_VALUE


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


def _collect_resource_type_counts(resource: dict[str, Any], counts: dict[str, int]) -> None:
    resource_type = str(resource.get("resourceType", "")).strip()
    if resource_type:
        counts[resource_type] = int(counts.get(resource_type, 0)) + 1

    contained = resource.get("contained")
    if isinstance(contained, list):
        for nested in contained:
            if isinstance(nested, dict):
                _collect_resource_type_counts(nested, counts)


def _resource_type_counts_from_entries(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        resource = entry.get("resource")
        if isinstance(resource, dict):
            _collect_resource_type_counts(resource, counts)
    return dict(sorted(counts.items(), key=lambda item: item[0]))


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

    suggestions = coding_assistant.suggest_codes(record)

    claims: DocumentReferenceClaims = {
        DocumentReferenceClaim.IDENTIFIER: document_id,
        DocumentReferenceClaim.SUBJECT: record.subject_id,
        DocumentReferenceClaim.AUTHOR: "",
        DocumentReferenceClaim.DATE: record.timestamp or datetime.now(timezone.utc).isoformat(),
        DocumentReferenceClaim.TYPE: _resolved_document_type(record),
        DocumentReferenceClaim.CATEGORY: _resolved_document_category(record),
        DocumentReferenceClaim.DESCRIPTION: _document_description(record),
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
    composition_loinc = _resolved_composition_type(section, composition_type_code)

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


def _diagnostic_report_resource(
    *,
    context: AdapterContext,
    record: CanonicalRecord,
) -> dict[str, Any] | None:
    claims = {
        key: str(value or "").strip()
        for key, value in record.flat_claims.items()
        if str(key or "").startswith("DiagnosticReport.") and str(value or "").strip()
    }
    if not claims:
        return None
    report_id = stable_uuid(
        context.manufacturer,
        context.tenant_id,
        record.subject_id,
        "diagnostic-report",
        record.source_id,
        record.timestamp,
        claims.get(DiagnosticReportClaim.CODE_TEXT, ""),
    )
    return {
        "resourceType": "DiagnosticReport",
        "id": report_id,
        "meta": {
            "claims": {
                "@context": FHIR_API_CONTEXT,
                **claims,
            }
        },
    }


def _claims_for_resource(record: CanonicalRecord, resource_type: str) -> dict[str, str]:
    prefix = f"{resource_type}."
    return {
        str(key): str(value or "").strip()
        for key, value in record.flat_claims.items()
        if str(key or "").startswith(prefix) and str(value or "").strip()
    }


def _codeable_concept(code: str, text: str) -> dict[str, Any]:
    token = str(code or "").strip()
    label = str(text or "").strip()
    concept: dict[str, Any] = {}
    if token:
        if "|" in token:
            system, value = token.split("|", 1)
            concept["coding"] = [{"system": system, "code": value}]
        else:
            concept["coding"] = [{"code": token}]
    if label:
        concept["text"] = label
    return concept


def _financial_resources(
    *,
    context: AdapterContext,
    subject: str,
    records: list[CanonicalRecord],
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    invoice_claims: dict[str, str] = {}
    for record in records:
        for key, value in _claims_for_resource(record, "Invoice").items():
            invoice_claims.setdefault(key, value)
    invoice_identifier = invoice_claims.get(InvoiceClaim.IDENTIFIER, "").strip()
    if not invoice_identifier:
        return None

    invoice_id = stable_uuid(
        context.manufacturer,
        context.tenant_id,
        subject,
        "invoice",
        invoice_identifier,
    )
    charge_items: list[dict[str, Any]] = []
    for record in records:
        claims = _claims_for_resource(record, "ChargeItem")
        if not claims:
            continue
        charge_identifier = claims.get(ChargeItemClaim.IDENTIFIER, "").strip() or stable_uuid(
            context.manufacturer,
            context.tenant_id,
            subject,
            invoice_identifier,
            "charge-item",
            record.source_id,
        )
        charge_id = stable_uuid(
            context.manufacturer,
            context.tenant_id,
            subject,
            invoice_identifier,
            "charge-item",
            charge_identifier,
        )
        claims.setdefault(ChargeItemClaim.IDENTIFIER, charge_identifier)
        claims.setdefault(ChargeItemClaim.STATUS, "billable")
        claims.setdefault(ChargeItemClaim.SUBJECT, subject)
        claims[ChargeItemClaim.SUPPORTING_INFORMATION] = f"urn:uuid:{invoice_id}"
        resource: dict[str, Any] = {
            "resourceType": "ChargeItem",
            "id": charge_id,
            "meta": {"claims": {"@context": FHIR_API_CONTEXT, **claims}},
            "identifier": [{"value": charge_identifier}],
            "status": claims[ChargeItemClaim.STATUS],
            "code": _codeable_concept(
                claims.get(ChargeItemClaim.CODE, ""),
                claims.get(ChargeItemClaim.CODE_TEXT, ""),
            ),
            "subject": {"reference": claims[ChargeItemClaim.SUBJECT]},
            "supportingInformation": [{"reference": f"urn:uuid:{invoice_id}"}],
        }
        occurrence = claims.get(ChargeItemClaim.OCCURRENCE, "").strip()
        if occurrence:
            resource["occurrenceDateTime"] = occurrence
        part_of = claims.get(ChargeItemClaim.PART_OF, "").strip()
        if part_of:
            resource["partOf"] = [{"reference": part_of}]
        quantity_number = claims.get(ChargeItemClaim.QUANTITY_NUMBER, "").strip()
        quantity_unit = claims.get(ChargeItemClaim.QUANTITY_UNIT, "").strip()
        if quantity_number or quantity_unit:
            quantity: dict[str, Any] = {}
            if quantity_number:
                try:
                    quantity["value"] = float(quantity_number)
                except ValueError:
                    quantity["value"] = quantity_number
            if quantity_unit:
                quantity["unit"] = quantity_unit
                quantity["code"] = quantity_unit
                quantity["system"] = "http://unitsofmeasure.org"
            resource["quantity"] = quantity
        charge_items.append(resource)

    charge_items.sort(key=lambda item: str(item.get("id", "")))
    invoice_claims.setdefault(InvoiceClaim.STATUS, "issued")
    invoice_claims.setdefault(InvoiceClaim.SUBJECT, subject)
    invoice: dict[str, Any] = {
        "resourceType": "Invoice",
        "id": invoice_id,
        "meta": {"claims": {"@context": FHIR_API_CONTEXT, **invoice_claims}},
        "identifier": [{"value": invoice_identifier}],
        "status": invoice_claims[InvoiceClaim.STATUS],
        "subject": {"reference": invoice_claims[InvoiceClaim.SUBJECT]},
        "lineItem": [
            {
                "sequence": index,
                "chargeItemReference": {"reference": f"urn:uuid:{item['id']}"},
            }
            for index, item in enumerate(charge_items, start=1)
        ],
    }
    issued_at = invoice_claims.get(InvoiceClaim.DATE, "").strip()
    if issued_at:
        invoice["date"] = issued_at
    return (invoice, charge_items)


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


def _record_has_encounter_signal(record: CanonicalRecord) -> bool:
    section = str(record.section or "").strip().lower()
    family = str(record.family or "").strip().lower()
    return any(value and value != DEFAULT_UNCODED_VALUE for value in (section, family))


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


def _subject_claims(
    *,
    context: AdapterContext,
    record: CanonicalRecord,
    subject_link_identifiers: list[str] | None = None,
) -> tuple[str, SubjectClaims]:
    subject_resource_id = stable_uuid(
        context.manufacturer,
        context.tenant_id,
        record.subject_id,
        "subject",
    )
    claims: SubjectClaims = {
        SubjectClaim.ID: record.subject_id,
        SubjectClaim.ACTIVE: "true",
        SubjectClaim.LANGUAGE: context.language,
    }
    links = sorted({value.strip() for value in (subject_link_identifiers or []) if value and value.strip()})
    if links:
        claims[SubjectClaim.LINK] = ",".join(links)
    birthyear = str(record.subject_birthyear or "").strip()
    if birthyear:
        claims[SubjectClaim.BIRTHYEAR] = birthyear
    birthsex = str(record.subject_birthsex or "").strip()
    if birthsex:
        claims[SubjectClaim.BIRTHSEX] = birthsex
    subject_kind = (context.subject_kind or "animal").strip().lower()
    if subject_kind in {"animal", "species"}:
        species_code = str(record.species_fhir_code or "").strip()
        if species_code:
            claims[AnimalClaim.SPECIES] = f"{context.fhir_species_system}|{species_code}"
        breed_code = str(record.animal_breed_code or "").strip()
        if breed_code:
            claims[AnimalClaim.BREED] = breed_code
        gender_status_code = str(record.animal_gender_status_code or "").strip()
        if gender_status_code:
            claims[AnimalClaim.GENDER_STATUS] = gender_status_code
    return subject_resource_id, claims


def _subject_resource(
    subject_resource_id: str,
    claims: SubjectClaims,
    contained: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "resourceType": "Subject",
        "id": subject_resource_id,
        "meta": {
            "claims": claims,
        },
        "contained": contained,
    }


def _research_subject_resource(
    subject_resource_id: str,
    subject_identifier: str,
    subject_claims: SubjectClaims,
    contained: list[dict[str, Any]],
) -> dict[str, Any]:
    compositions = [
        item for item in contained
        if isinstance(item, dict) and item.get("resourceType") == "Composition"
    ]
    claims = dict(subject_claims)
    claims[ResearchSubjectClaim.IDENTIFIER] = subject_identifier
    claims[ResearchSubjectClaim.STATUS] = "candidate"
    logical_id = (
        subject_identifier.removeprefix("urn:uuid:")
        if subject_identifier.startswith("urn:uuid:")
        else subject_resource_id
    )
    resource: dict[str, Any] = {
        "resourceType": "ResearchSubject",
        "id": logical_id,
        "meta": {"claims": claims},
        ResearchSubjectClaim.IDENTIFIER: subject_identifier,
        ResearchSubjectClaim.STATUS: "candidate",
        "contained": contained,
    }
    if compositions:
        resource["composition"] = compositions[0]
    return resource


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
    diagnostic_report_entries_count = 0
    invoice_entries_count = 0
    charge_item_entries_count = 0
    encounter_entries_count = 0
    related_person_entries_count = 0
    subject_entries_count = 0
    research_subject_entries_count = 0
    composition_entries_count = 0
    grouped_doc_resources: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    grouped_diagnostic_report_resources: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    grouped_invoice_resources: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    grouped_charge_item_resources: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    grouped_financial_records: dict[tuple[str, str, str], list[CanonicalRecord]] = defaultdict(list)
    grouped_encounter_resources: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    grouped_related_resources: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    grouped_subject_link_identifiers: dict[str, set[str]] = defaultdict(set)
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

        diagnostic_report = _diagnostic_report_resource(context=context, record=record)
        if diagnostic_report is not None:
            diagnostic_report_id = str(diagnostic_report["id"])
            grouped_diagnostic_report_resources[key][diagnostic_report_id] = diagnostic_report
            diagnostic_report_entries_count += 1

        invoice_identifier = record.flat_claims.get(InvoiceClaim.IDENTIFIER, "").strip()
        if invoice_identifier:
            grouped_financial_records[(record.subject_id, record.composition_section, invoice_identifier)].append(record)

        if _record_has_encounter_signal(record):
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
                grouped_subject_link_identifiers[record.subject_id].add(owner_identifier)
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

    for (subject, section, _), financial_records in grouped_financial_records.items():
        resources = _financial_resources(
            context=context,
            subject=subject,
            records=financial_records,
        )
        if resources is None:
            continue
        invoice, charge_items = resources
        key = (subject, section)
        grouped_invoice_resources[key][str(invoice["id"])] = invoice
        for item in charge_items:
            grouped_charge_item_resources[key][str(item["id"])] = item
        invoice_entries_count += 1
        charge_item_entries_count += len(charge_items)

    subject_entries: list[dict[str, Any]] = []
    for subject in sorted(subjects):
        contained_resources: list[dict[str, Any]] = []
        related_ids = sorted(grouped_related_resources[subject].keys())

        for section in sorted(subject_sections[subject]):
            key = (subject, section)
            doc_resources_map = grouped_doc_resources[key]
            diagnostic_report_resources_map = grouped_diagnostic_report_resources[key]
            invoice_resources_map = grouped_invoice_resources[key]
            charge_item_resources_map = grouped_charge_item_resources[key]
            encounter_resources_map = grouped_encounter_resources[key]
            doc_ids = sorted(doc_resources_map.keys())
            diagnostic_report_ids = sorted(diagnostic_report_resources_map.keys())
            invoice_ids = sorted(invoice_resources_map.keys())
            charge_item_ids = sorted(charge_item_resources_map.keys())
            encounter_ids = sorted(encounter_resources_map.keys())
            entry_ids = encounter_ids + diagnostic_report_ids + invoice_ids + charge_item_ids + doc_ids
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
            for resource_id in diagnostic_report_ids:
                contained_resources.append(diagnostic_report_resources_map[resource_id])
            for resource_id in invoice_ids:
                contained_resources.append(invoice_resources_map[resource_id])
            for resource_id in charge_item_ids:
                contained_resources.append(charge_item_resources_map[resource_id])
            for resource_id in doc_ids:
                contained_resources.append(doc_resources_map[resource_id])

        for related_id in related_ids:
            contained_resources.append(grouped_related_resources[subject][related_id])

        subject_record = latest_record_by_subject[subject]
        subject_resource_id, subject_claims = _subject_claims(
            context=context,
            record=subject_record,
            subject_link_identifiers=sorted(grouped_subject_link_identifiers[subject]),
        )
        if str(context.data_use or "").strip().lower() == "secondary":
            subject_entries.append(
                jsonapi_resource_entry(
                    _research_subject_resource(
                        subject_resource_id=subject_resource_id,
                        subject_identifier=subject,
                        subject_claims=subject_claims,
                        contained=contained_resources,
                    )
                )
            )
            research_subject_entries_count += 1
        else:
            subject_entries.append(
                jsonapi_resource_entry(
                    _subject_resource(
                        subject_resource_id=subject_resource_id,
                        claims=subject_claims,
                        contained=contained_resources,
                    )
                )
            )
        subject_entries_count += 1

    outcome_entries = _operation_outcome_entries(
        context=context,
        row_issues=[item for item in (row_issues or []) if isinstance(item, dict)],
    )
    bundle_entries = subject_entries + outcome_entries

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
        "diagnosticReportEntries": diagnostic_report_entries_count,
        "invoiceEntries": invoice_entries_count,
        "chargeItemEntries": charge_item_entries_count,
        "encounterEntries": encounter_entries_count,
        "relatedPersonEntries": related_person_entries_count,
        "subjectEntries": subject_entries_count,
        "researchSubjectEntries": research_subject_entries_count,
        "patientEntries": subject_entries_count - research_subject_entries_count,
        "compositionEntries": composition_entries_count,
        "operationOutcomeEntries": len(outcome_entries),
        "resourceTypeCounts": _resource_type_counts_from_entries(bundle_entries),
        "logComposition": bool(getattr(context, "log_composition", False)),
        "families": dict(sorted(families.items(), key=lambda item: (-item[1], item[0]))),
        "sections": dict(sorted(sections.items(), key=lambda item: (-item[1], item[0]))),
    }

    return PipelineResult(
        composition_message=composition_message,
        summary=summary,
    )
