# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from .base import CodingSuggestion
from ..models import CanonicalRecord


class RuleBasedCodingAssistant:
    """Simple deterministic coding suggestions.

    This is only a bridge until a real AI/ML pipeline is plugged in.
    """

    def suggest_codes(self, record: CanonicalRecord) -> list[CodingSuggestion]:
        family = (record.family or "").strip().lower()
        section = (record.section or "").strip().lower()
        subfamily = (record.subfamily or "").strip().lower()

        suggestions: list[CodingSuggestion] = []

        if "vacuna" in family or "vacuna" in subfamily:
            suggestions.append(
                CodingSuggestion(
                    system="http://snomed.info/sct",
                    code="787859002",
                    display="Vaccine product",
                    confidence=0.72,
                    evidence=f"family={record.family}; subfamily={record.subfamily}",
                )
            )

        if "laboratorio" in family:
            suggestions.append(
                CodingSuggestion(
                    system="http://loinc.org",
                    code="26436-6",
                    display="Laboratory studies",
                    confidence=0.68,
                    evidence=f"family={record.family}",
                )
            )

        if "diagnostico por imagen" in family:
            suggestions.append(
                CodingSuggestion(
                    system="http://dicom.nema.org/resources/ontology/DCM",
                    code="IMG",
                    display="Imaging procedure",
                    confidence=0.66,
                    evidence=f"family={record.family}",
                )
            )

        if section == "clinica" and "consulta" in family:
            suggestions.append(
                CodingSuggestion(
                    system="http://loinc.org",
                    code="60591-5",
                    display="Patient summary",
                    confidence=0.6,
                    evidence=f"section={record.section}; family={record.family}",
                )
            )

        return suggestions
