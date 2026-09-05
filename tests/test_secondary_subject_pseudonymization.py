# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.

from adapter_ingestion.manufacturers.tabular_xlsx import TabularXlsxAdapter
from adapter_ingestion.models import AdapterContext
import pytest


def test_secondary_subject_identifier_uses_confidential_resolver_before_becoming_twin_uuid() -> None:
    resolved: list[str] = []

    def resolve(external_identifier: str) -> str:
        resolved.append(external_identifier)
        return "11111111-1111-4111-8111-111111111111"

    context = AdapterContext(
        manufacturer="clinic-system",
        tenant_id="7654321",
        jurisdiction="CA-BC",
        sector="animal-research",
        issuer_did="did:web:issuer.example",
        audience_did="did:web:audience.example",
        data_use="secondary",
        personal_id_resolver=resolve,
    )

    subject = TabularXlsxAdapter()._subject_id(context, "chip-991", None)

    assert subject == "urn:uuid:11111111-1111-4111-8111-111111111111"
    assert resolved == ["chip-991"]


def test_secondary_subject_accepts_an_already_pseudonymous_uuid_without_link_lookup() -> None:
    context = AdapterContext(
        manufacturer="clinic-system",
        tenant_id="7654321",
        jurisdiction="CA-BC",
        sector="animal-research",
        issuer_did="did:web:issuer.example",
        audience_did="did:web:audience.example",
        data_use="secondary",
        personal_id_resolver=lambda _: (_ for _ in ()).throw(AssertionError("resolver must not run")),
    )

    subject = TabularXlsxAdapter()._subject_id(
        context,
        "urn:uuid:11111111-1111-4111-8111-111111111111",
        None,
    )

    assert subject == "urn:uuid:11111111-1111-4111-8111-111111111111"


def test_secondary_subject_rejects_an_identifying_value_without_confidential_link_store() -> None:
    context = AdapterContext(
        manufacturer="clinic-system",
        tenant_id="7654321",
        jurisdiction="CA-BC",
        sector="animal-research",
        issuer_did="did:web:issuer.example",
        audience_did="did:web:audience.example",
        data_use="secondary",
    )

    with pytest.raises(ValueError, match="confidential subject identifier resolver"):
        TabularXlsxAdapter()._subject_id(context, "chip-991", None)
