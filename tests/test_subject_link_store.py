# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.

from __future__ import annotations

import base64

from adapter_ingestion.subject_links import (
    InMemorySubjectLinkRecordStore,
    ProtectedSubjectLinkStore,
    SubjectLinkScope,
)


def _key() -> str:
    return base64.urlsafe_b64encode(bytes(range(32))).decode("ascii").rstrip("=")


def test_subject_link_is_stable_inside_exact_storage_scope_without_plaintext_persistence() -> None:
    records = InMemorySubjectLinkRecordStore()
    links = ProtectedSubjectLinkStore(records=records, key_base64url=_key())
    scope = SubjectLinkScope(
        network_kind="test-network",
        jurisdiction="CA-BC",
        sector="animal-research",
        tenant_id="7654321",
    )

    first = links.resolve_or_create(scope=scope, source_system="clinic-system", external_identifier="chip-991")
    second = links.resolve_or_create(scope=scope, source_system="clinic-system", external_identifier="chip-991")

    assert second == first
    persisted = records.list_records()
    assert len(persisted) == 1
    serialized = repr(persisted[0])
    assert "chip-991" not in serialized
    assert first not in serialized


def test_subject_link_does_not_cross_network_or_jurisdiction_boundaries() -> None:
    records = InMemorySubjectLinkRecordStore()
    links = ProtectedSubjectLinkStore(records=records, key_base64url=_key())
    base = dict(sector="animal-research", tenant_id="7654321")

    local = links.resolve_or_create(
        scope=SubjectLinkScope(network_kind="local-network", jurisdiction="CA-BC", **base),
        source_system="clinic-system",
        external_identifier="chip-991",
    )
    staging = links.resolve_or_create(
        scope=SubjectLinkScope(network_kind="test-network", jurisdiction="CA-BC", **base),
        source_system="clinic-system",
        external_identifier="chip-991",
    )
    other_jurisdiction = links.resolve_or_create(
        scope=SubjectLinkScope(network_kind="test-network", jurisdiction="CA-ON", **base),
        source_system="clinic-system",
        external_identifier="chip-991",
    )

    assert len({local, staging, other_jurisdiction}) == 3


def test_subject_link_requires_a_32_byte_protection_key() -> None:
    short_key = base64.urlsafe_b64encode(b"short").decode("ascii").rstrip("=")
    try:
        ProtectedSubjectLinkStore(records=InMemorySubjectLinkRecordStore(), key_base64url=short_key)
    except ValueError as error:
        assert str(error) == "subject link protection key must decode to 32 bytes"
    else:
        raise AssertionError("invalid protection key was accepted")
