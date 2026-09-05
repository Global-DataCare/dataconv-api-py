# Flow contract: the confidential identifier link uses a dedicated store and never shares the searchable twin vault.

from __future__ import annotations

import base64
from dataclasses import replace

import pytest

from adapter_ingestion.service.factory import build_subject_link_store
from adapter_ingestion.service.settings import load_settings
from adapter_ingestion.subject_links import InMemorySubjectLinkRecordStore


def _key() -> str:
    return base64.urlsafe_b64encode(b"s" * 32).decode("ascii").rstrip("=")


def test_memory_provider_builds_a_separate_protected_subject_link_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_PROVIDER", "mem")
    monkeypatch.setenv("SUBJECT_LINK_PROTECTION_KEY", _key())
    settings = load_settings()

    store = build_subject_link_store(settings)

    assert isinstance(store._records, InMemorySubjectLinkRecordStore)


def test_persistent_provider_requires_an_explicit_subject_link_protection_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SUBJECT_LINK_PROTECTION_KEY", raising=False)
    settings = replace(load_settings(), db_provider="firestore", subject_link_protection_key="")

    with pytest.raises(ValueError, match="SUBJECT_LINK_PROTECTION_KEY"):
        build_subject_link_store(settings)
