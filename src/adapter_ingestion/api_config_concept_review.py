"""Row-level review queue derived from embedded API-CONFIG semantics."""

# Copyright ConnectHealth.info (Connecting Solution & Applications Ltd.)
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from gdc_data_utils import (
    AllergyIntoleranceClaim,
    ConditionClaim,
    DiagnosticReportClaim,
    ImmunizationClaim,
    MedicationStatementClaim,
    ProcedureClaim,
)

from .source_concept_classification import classify_source_concept


MAPPED_LOCAL_TEXT_RESOURCE_TYPES = {
    AllergyIntoleranceClaim.CODE_TEXT: "AllergyIntolerance",
    ConditionClaim.CODE_TEXT: "Condition",
    DiagnosticReportClaim.CODE_TEXT: "DiagnosticReport",
    ImmunizationClaim.VACCINE_CODE_TEXT: "Immunization",
    MedicationStatementClaim.CODE_TEXT: "MedicationStatement",
    ProcedureClaim.CODE_TEXT: "Procedure",
}


@dataclass(frozen=True)
class ConceptReviewRow:
    sheet: str
    row_number: int
    resource_type: str
    source_text: str
    confidence: str
    basis: str
    section: str
    family: str
    subfamily: str


@dataclass(frozen=True)
class ConceptReviewResult:
    rows: tuple[ConceptReviewRow, ...]
    counts_by_resource_type: dict[str, int]
    counts_by_sheet: dict[str, int]


def _marker_value(marker: object, key: str) -> str:
    prefix = f"{key}="
    for token in str(marker or "").replace(";", ":").split(":"):
        if token.startswith(prefix):
            return token[len(prefix) :].strip()
    return ""


def classify_workbook(path: Path | str) -> ConceptReviewResult:
    """Read a prepared workbook and return candidates without modifying it."""

    from openpyxl import load_workbook

    workbook = load_workbook(Path(path), read_only=True, data_only=True)
    rows: list[ConceptReviewRow] = []
    counts_by_sheet: Counter[str] = Counter()
    try:
        for sheet in workbook.worksheets:
            marker = sheet.cell(1, 1).value
            subject_kind = _marker_value(marker, "subjectKind")
            mappings = [str(cell.value or "").strip() for cell in sheet[2]]
            columns = {mapping: index for index, mapping in enumerate(mappings) if mapping}
            if not any(
                field in columns
                for field in ("concept", "treatment", *MAPPED_LOCAL_TEXT_RESOURCE_TYPES)
            ):
                continue
            for row_number, values in enumerate(
                sheet.iter_rows(min_row=4, values_only=True),
                start=4,
            ):
                def value(field: str) -> object:
                    index = columns.get(field)
                    return values[index] if index is not None and index < len(values) else ""

                section = str(value("section") or "").strip()
                family = str(value("family") or "").strip()
                subfamily = str(value("subfamily") or "").strip()
                concept = str(value("concept") or "").strip()
                treatment = str(value("treatment") or "").strip()
                mapped_texts = [
                    (resource_type, str(value(claim) or "").strip())
                    for claim, resource_type in MAPPED_LOCAL_TEXT_RESOURCE_TYPES.items()
                    if str(value(claim) or "").strip()
                ]
                if not concept and not treatment and not mapped_texts:
                    continue
                emitted: set[tuple[str, str]] = set()
                for resource_type, source_text in mapped_texts:
                    key = (resource_type, source_text)
                    emitted.add(key)
                    rows.append(ConceptReviewRow(
                        sheet=sheet.title,
                        row_number=row_number,
                        resource_type=resource_type,
                        source_text=source_text,
                        confidence="mapped",
                        basis="explicit canonical local code-text mapping",
                        section=section,
                        family=family,
                        subfamily=subfamily,
                    ))
                    counts_by_sheet[sheet.title] += 1
                inferred_candidates = () if mapped_texts else classify_source_concept(
                    section=section,
                    family=family,
                    subfamily=subfamily,
                    concept=concept,
                    treatment=treatment,
                    subject_kind=subject_kind,
                )
                for candidate in inferred_candidates:
                    if not candidate.source_text:
                        continue
                    if (candidate.resource_type, candidate.source_text) in emitted:
                        continue
                    rows.append(ConceptReviewRow(
                        sheet=sheet.title,
                        row_number=row_number,
                        resource_type=candidate.resource_type,
                        source_text=candidate.source_text,
                        confidence=candidate.confidence,
                        basis=candidate.basis,
                        section=section,
                        family=family,
                        subfamily=subfamily,
                    ))
                    counts_by_sheet[sheet.title] += 1
    finally:
        workbook.close()
    counts_by_resource = Counter(item.resource_type for item in rows)
    return ConceptReviewResult(
        rows=tuple(rows),
        counts_by_resource_type=dict(sorted(counts_by_resource.items())),
        counts_by_sheet=dict(sorted(counts_by_sheet.items())),
    )
