# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
import base64
from hashlib import sha256
import hmac
import json
import os
from threading import Lock
from typing import Protocol
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _normalized(value: str, *, upper: bool = False) -> str:
    text = str(value or "").strip()
    return text.upper() if upper else text.lower()


@dataclass(frozen=True)
class SubjectLinkScope:
    """Internal storage boundary; none of these dimensions modifies public tenant_id."""

    network_kind: str
    jurisdiction: str
    sector: str
    tenant_id: str

    def canonical(self) -> str:
        values = {
            "jurisdiction": _normalized(self.jurisdiction, upper=True),
            "networkKind": _normalized(self.network_kind),
            "sector": _normalized(self.sector),
            "tenantId": str(self.tenant_id or "").strip(),
        }
        if not all(values.values()):
            raise ValueError("subject link scope requires network_kind, jurisdiction, sector and tenant_id")
        return json.dumps(values, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True)
class ProtectedSubjectLinkRecord:
    id: str
    nonce_base64url: str
    ciphertext_base64url: str
    key_version: str = "v1"


class SubjectLinkRecordStore(Protocol):
    def get(self, record_id: str) -> ProtectedSubjectLinkRecord | None: ...

    def create_if_absent(self, record: ProtectedSubjectLinkRecord) -> ProtectedSubjectLinkRecord: ...


class InMemorySubjectLinkRecordStore:
    def __init__(self) -> None:
        self._records: dict[str, ProtectedSubjectLinkRecord] = {}
        self._lock = Lock()

    def get(self, record_id: str) -> ProtectedSubjectLinkRecord | None:
        return self._records.get(record_id)

    def create_if_absent(self, record: ProtectedSubjectLinkRecord) -> ProtectedSubjectLinkRecord:
        with self._lock:
            existing = self._records.get(record.id)
            if existing is not None:
                return existing
            self._records[record.id] = record
            return record

    def list_records(self) -> list[ProtectedSubjectLinkRecord]:
        return list(self._records.values())


def _decode_key(value: str) -> bytes:
    raw = str(value or "").strip()
    try:
        padded = raw + "=" * ((4 - len(raw) % 4) % 4)
        key = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as error:
        raise ValueError("subject link protection key must be base64url") from error
    if len(key) != 32:
        raise ValueError("subject link protection key must decode to 32 bytes")
    return key


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _from_base64url(value: str) -> bytes:
    padded = value + "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


class ProtectedSubjectLinkStore:
    """Maps an identifying source value to a random twin UUID without plaintext persistence."""

    def __init__(
        self,
        *,
        records: SubjectLinkRecordStore,
        key_base64url: str,
        key_version: str = "v1",
    ) -> None:
        self._records = records
        self._key = _decode_key(key_base64url)
        self._cipher = AESGCM(self._key)
        self._key_version = str(key_version or "").strip() or "v1"

    def _identity(self, *, scope: SubjectLinkScope, source_system: str, external_identifier: str) -> tuple[str, bytes]:
        source = _normalized(source_system)
        external = str(external_identifier or "").strip()
        if not source or not external:
            raise ValueError("subject link requires source_system and external_identifier")
        canonical = json.dumps(
            {
                "externalIdentifier": external,
                "scope": json.loads(scope.canonical()),
                "sourceSystem": source,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        digest = hmac.new(self._key, canonical, sha256).hexdigest()
        return digest, canonical

    def _decrypt_uuid(self, record: ProtectedSubjectLinkRecord, *, aad: bytes) -> str:
        payload = self._cipher.decrypt(
            _from_base64url(record.nonce_base64url),
            _from_base64url(record.ciphertext_base64url),
            aad,
        )
        decoded = json.loads(payload.decode("utf-8"))
        return str(uuid.UUID(str(decoded["twinUuid"])))

    def resolve_or_create(
        self,
        *,
        scope: SubjectLinkScope,
        source_system: str,
        external_identifier: str,
    ) -> str:
        record_id, aad = self._identity(
            scope=scope,
            source_system=source_system,
            external_identifier=external_identifier,
        )
        existing = self._records.get(record_id)
        if existing is not None:
            return self._decrypt_uuid(existing, aad=aad)

        twin_uuid = str(uuid.uuid4())
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(
            nonce,
            json.dumps({"twinUuid": twin_uuid}, separators=(",", ":")).encode("utf-8"),
            aad,
        )
        stored = self._records.create_if_absent(
            ProtectedSubjectLinkRecord(
                id=record_id,
                nonce_base64url=_base64url(nonce),
                ciphertext_base64url=_base64url(ciphertext),
                key_version=self._key_version,
            )
        )
        return self._decrypt_uuid(stored, aad=aad)
