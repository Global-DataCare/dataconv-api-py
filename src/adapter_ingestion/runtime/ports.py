# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import ConfigKey, JobRecord, StoredConfig


class ConfigStore(ABC):
    @abstractmethod
    def put(self, config: StoredConfig) -> StoredConfig:
        raise NotImplementedError

    @abstractmethod
    def get(self, key: ConfigKey) -> StoredConfig | None:
        raise NotImplementedError


class JobStore(ABC):
    @abstractmethod
    def put(self, job: JobRecord) -> JobRecord:
        raise NotImplementedError

    @abstractmethod
    def get(self, job_id: str) -> JobRecord | None:
        raise NotImplementedError

    @abstractmethod
    def find_by_thid(self, thid: str) -> JobRecord | None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, job_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list(self) -> list[JobRecord]:
        raise NotImplementedError


class JobQueue(ABC):
    @abstractmethod
    def enqueue(self, job_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def dequeue(self) -> str | None:
        raise NotImplementedError


class BlobStore(ABC):
    @abstractmethod
    def put_bytes(
        self,
        *,
        path: str,
        payload: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_bytes(self, ref: str) -> bytes:
        raise NotImplementedError


class IVaultRepository(ABC):
    @abstractmethod
    def put(self, collection_name: str, documents: list[dict[str, Any]], section_id: str = "default") -> bool:
        raise NotImplementedError

    @abstractmethod
    def get(self, collection_name: str, doc_id: str, section_id: str = "default") -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, collection_name: str, doc_id: str, section_id: str = "default") -> bool:
        raise NotImplementedError

    @abstractmethod
    def query(self, collection_name: str, filters: dict[str, str], section_id: str = "default") -> list[dict[str, Any]]:
        raise NotImplementedError


class ISearchRepository(ABC):
    @abstractmethod
    def upsert(self, *, vault_id: str, resource_type: str, resource: dict[str, Any]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def search(
        self,
        *,
        vault_id: str,
        resource_type: str,
        search_params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, *, vault_id: str, resource_type: str, resource_id: str) -> bool:
        raise NotImplementedError
