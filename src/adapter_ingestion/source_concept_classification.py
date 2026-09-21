"""Review-only resource candidates for heterogeneous tabular source concepts."""

# Copyright ConnectHealth.info (Connecting Solution & Applications Ltd.)
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class SourceConceptCandidate:
    resource_type: str
    source_text: str
    confidence: str
    basis: str
    subject_species: str = ""
    subject_sex: str = ""


def _normalized(value: object) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    plain = "".join(character for character in decomposed if not unicodedata.combining(character))
    return " ".join(plain.casefold().split())


def _lines(value: object) -> tuple[str, ...]:
    return tuple(line.strip() for line in re.split(r"[\r\n]+", str(value or "")) if line.strip())


def _candidate(resource_type: str, source_text: str, confidence: str, basis: str) -> SourceConceptCandidate:
    return SourceConceptCandidate(
        resource_type=resource_type,
        source_text=source_text,
        confidence=confidence,
        basis=basis,
    )


def classify_source_concept(
    *,
    section: object,
    family: object,
    subfamily: object,
    concept: object,
    treatment: object = "",
    subject_kind: str = "",
) -> tuple[SourceConceptCandidate, ...]:
    """Return non-authoritative candidates without inferring demographics.

    The rules intentionally consume semantic coordinates rather than sheet or
    vendor names. They identify the review queue only; terminology selection
    and final resource creation remain separate human-confirmed phases.
    """

    del subject_kind  # Classification never fabricates species or sex from subject kind.
    treatment_lines = _lines(treatment)
    if treatment_lines:
        candidates: list[SourceConceptCandidate] = []
        for line in treatment_lines:
            token = _normalized(line)
            if any(word in token for word in ("gota", "comprim", "capsul", "mg", "ml", "cada ", "veces al dia")):
                candidates.append(_candidate(
                    "MedicationStatement",
                    line,
                    "medium",
                    "dose or administration wording in treatment line; requires review of prescription versus reported use",
                ))
            elif any(word in token for word in ("sedacion", "cirugia", "ecografia", "radiografia", "castracion", "limpieza")):
                candidates.append(_candidate(
                    "Procedure",
                    line,
                    "medium",
                    "procedure wording in treatment line",
                ))
            else:
                candidates.extend((
                    _candidate("Procedure", line, "ambiguous", "unstructured treatment may describe a performed procedure"),
                    _candidate("MedicationStatement", line, "ambiguous", "unstructured treatment may describe medication use"),
                ))
        return tuple(candidates)

    source_text = str(concept or "").strip()
    coordinates = " ".join(
        _normalized(value) for value in (section, family, subfamily, concept) if str(value or "").strip()
    )
    if any(word in coordinates for word in ("vacuna", "vacunacion", "rabia", "inmunizacion")):
        return (_candidate("Immunization", source_text, "medium", "vaccination hierarchy or administration wording"),)
    if any(word in coordinates for word in ("sedacion", "cirugia", "ecografia", "radiografia", "castracion")):
        return (_candidate("Procedure", source_text, "medium", "procedure hierarchy or wording"),)
    if any(word in coordinates for word in ("analisis", "laboratorio", "hemograma", "bioquimica")):
        return (_candidate("DiagnosticReport", source_text, "medium", "laboratory or analysis hierarchy"),)
    if any(word in coordinates for word in ("consulta", "visita", "urgencia")):
        return (_candidate("Encounter", source_text, "medium", "encounter hierarchy or wording"),)
    if any(word in coordinates for word in ("medicamento", "farmaco")):
        return (_candidate("MedicationStatement", source_text, "ambiguous", "medication hierarchy; dispense, order and use require review"),)
    if any(word in coordinates for word in ("tienda", "producto", "toallita", "aliment", "accesorio", "pienso")):
        return (_candidate("ChargeItem", source_text, "high", "retail product or charge hierarchy"),)
    return (_candidate("Unclassified", source_text, "pending", "no governed resource rule matched"),)
