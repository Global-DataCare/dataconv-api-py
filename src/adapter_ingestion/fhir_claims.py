# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

try:
    from typing import TypedDict
except ImportError:  # pragma: no cover - Python 3.7 fallback
    try:
        from typing_extensions import TypedDict  # type: ignore
    except Exception:  # pragma: no cover - last-resort runtime fallback
        def TypedDict(name, fields, total=True):  # type: ignore
            return dict


class DocumentReferenceClaim:
    IDENTIFIER = "DocumentReference.identifier"
    SUBJECT = "DocumentReference.subject"
    AUTHOR = "DocumentReference.author"
    DATE = "DocumentReference.date"
    TYPE = "DocumentReference.type"
    CATEGORY = "DocumentReference.category"
    DESCRIPTION = "DocumentReference.description"
    LANGUAGE = "DocumentReference.language"
    TEXT = "DocumentReference.text"
    EVENT_CODE = "DocumentReference.event-code"
    MODALITY = "DocumentReference.modality"


class CompositionClaim:
    IDENTIFIER = "Composition.identifier"
    SUBJECT = "Composition.subject"
    SECTION = "Composition.section"
    AUTHOR = "Composition.author"
    DATE = "Composition.date"
    TYPE = "Composition.type"
    TITLE = "Composition.title"
    ENTRY = "Composition.entry"


class RelatedPersonClaim:
    IDENTIFIER = "RelatedPerson.identifier"
    PATIENT = "RelatedPerson.patient"
    RELATIONSHIP = "RelatedPerson.relationship"
    ACTIVE = "RelatedPerson.active"
    NAME = "RelatedPerson.name"


class SubjectClaim:
    ID = "Subject.id"
    ACTIVE = "Subject.active"
    LANGUAGE = "Subject.language"
    LINK = "Subject.link"
    BIRTHYEAR = "Subject.birthyear"
    BIRTHSEX = "Subject.birthsex"


class ResearchSubjectClaim:
    IDENTIFIER = "ResearchSubject.identifier"
    STATUS = "ResearchSubject.status"


class AnimalClaim:
    SPECIES = "Subject.animal-species"
    BREED = "Subject.animal-breed"
    GENDER_STATUS = "Subject.animal-genderstatus"


class EncounterClaim:
    IDENTIFIER = "Encounter.identifier"
    SUBJECT = "Encounter.subject"
    DATE = "Encounter.date"
    STATUS = "Encounter.status"
    CLASS = "Encounter.class"
    SERVICE_TYPE = "Encounter.servicetype"


class OperationOutcomeClaim:
    CONTEXT = "@context"
    TYPE = "@type"
    ROW_NUMBER = "OperationOutcome.rowNumber"
    SECTION_FAMILY = "OperationOutcome.sectionFamily"
    ISSUE_CODE = "OperationOutcome.issueCode"


DocumentReferenceClaims = TypedDict(
    "DocumentReferenceClaims",
    {
        DocumentReferenceClaim.IDENTIFIER: str,
        DocumentReferenceClaim.SUBJECT: str,
        DocumentReferenceClaim.AUTHOR: str,
        DocumentReferenceClaim.DATE: str,
        DocumentReferenceClaim.TYPE: str,
        DocumentReferenceClaim.CATEGORY: str,
        DocumentReferenceClaim.DESCRIPTION: str,
        DocumentReferenceClaim.LANGUAGE: str,
        DocumentReferenceClaim.TEXT: str,
        DocumentReferenceClaim.EVENT_CODE: str,
        DocumentReferenceClaim.MODALITY: str,
    },
    total=False,
)


CompositionClaims = TypedDict(
    "CompositionClaims",
    {
        CompositionClaim.IDENTIFIER: str,
        CompositionClaim.SUBJECT: str,
        CompositionClaim.SECTION: str,
        CompositionClaim.AUTHOR: str,
        CompositionClaim.DATE: str,
        CompositionClaim.TYPE: str,
        CompositionClaim.TITLE: str,
        CompositionClaim.ENTRY: str,
    },
    total=False,
)


RelatedPersonClaims = TypedDict(
    "RelatedPersonClaims",
    {
        RelatedPersonClaim.IDENTIFIER: str,
        RelatedPersonClaim.PATIENT: str,
        RelatedPersonClaim.RELATIONSHIP: str,
        RelatedPersonClaim.ACTIVE: str,
        RelatedPersonClaim.NAME: str,
    },
    total=False,
)


SubjectClaims = TypedDict(
    "SubjectClaims",
    {
        SubjectClaim.ID: str,
        SubjectClaim.ACTIVE: str,
        SubjectClaim.LANGUAGE: str,
        SubjectClaim.LINK: str,
        SubjectClaim.BIRTHYEAR: str,
        SubjectClaim.BIRTHSEX: str,
        AnimalClaim.SPECIES: str,
        AnimalClaim.BREED: str,
        AnimalClaim.GENDER_STATUS: str,
    },
    total=False,
)


# Backwards compatibility for internal imports during the v1 -> v2 transition.
PatientClaim = SubjectClaim
PatientClaims = SubjectClaims


EncounterClaims = TypedDict(
    "EncounterClaims",
    {
        EncounterClaim.IDENTIFIER: str,
        EncounterClaim.SUBJECT: str,
        EncounterClaim.DATE: str,
        EncounterClaim.STATUS: str,
        EncounterClaim.CLASS: str,
        EncounterClaim.SERVICE_TYPE: str,
    },
    total=False,
)


OperationOutcomeClaims = TypedDict(
    "OperationOutcomeClaims",
    {
        OperationOutcomeClaim.CONTEXT: str,
        OperationOutcomeClaim.TYPE: str,
        OperationOutcomeClaim.ROW_NUMBER: str,
        OperationOutcomeClaim.SECTION_FAMILY: str,
        OperationOutcomeClaim.ISSUE_CODE: str,
    },
    total=False,
)
