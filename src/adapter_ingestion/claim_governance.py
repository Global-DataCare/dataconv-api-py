"""Governance for DataConv claims that are not yet owned by common-utils."""

DATACONV_CLAIM_ALIASES: dict[str, str] = {
    "Encounter.date": "Encounter.period-start",
    "Encounter.servicetype": "Encounter.type",
}

DATACONV_EXTENSION_CLAIMS: set[str] = {
    "DocumentReference.text",
    "OperationOutcome.issueCode",
    "OperationOutcome.rowNumber",
    "OperationOutcome.sectionFamily",
    "ResearchSubject.identifier",
    "ResearchSubject.status",
    "Subject.active",
    "Subject.animal-breed",
    "Subject.animal-genderstatus",
    "Subject.animal-species",
    "Subject.birthsex",
    "Subject.birthyear",
    "Subject.id",
    "Subject.language",
    "Subject.link",
}
