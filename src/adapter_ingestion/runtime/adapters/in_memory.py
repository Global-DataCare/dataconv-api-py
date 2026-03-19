# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections import deque

from ..models import ConfigKey, JobRecord, StoredConfig
from ..ports import BlobStore, ConfigStore, IVaultRepository, JobQueue, JobStore


class InMemoryConfigStore(ConfigStore):
    def __init__(self) -> None:
        self._items: dict[str, StoredConfig] = {}

    def put(self, config: StoredConfig) -> StoredConfig:
        key = config.key.normalized().as_token()
        self._items[key] = config
        return config

    def get(self, key: ConfigKey) -> StoredConfig | None:
        token = key.normalized().as_token()
        return self._items.get(token)


class InMemoryJobStore(JobStore):
    def __init__(self) -> None:
        self._items: dict[str, JobRecord] = {}

    def put(self, job: JobRecord) -> JobRecord:
        self._items[str(job.job_id)] = job
        return job

    def get(self, job_id: str) -> JobRecord | None:
        return self._items.get(str(job_id))

    def find_by_thid(self, thid: str) -> JobRecord | None:
        token = str(thid or "").strip()
        if not token:
            return None
        for item in self._items.values():
            if item.thid == token:
                return item
        return None

    def delete(self, job_id: str) -> bool:
        token = str(job_id or "").strip()
        if not token:
            return False
        return self._items.pop(token, None) is not None

    def list(self) -> list[JobRecord]:
        return list(self._items.values())


class InMemoryJobQueue(JobQueue):
    def __init__(self) -> None:
        self._queue: deque[str] = deque()

    def enqueue(self, job_id: str) -> None:
        self._queue.append(str(job_id))

    def dequeue(self) -> str | None:
        if not self._queue:
            return None
        return self._queue.popleft()


class InMemoryBlobStore(BlobStore):
    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    def put_bytes(
        self,
        *,
        path: str,
        payload: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        key = str(path or "").strip()
        if not key:
            raise ValueError("path is required")
        self._blobs[key] = bytes(payload)
        return f"mem://{key}"

    def get_bytes(self, ref: str) -> bytes:
        key = str(ref or "").strip()
        if key.startswith("mem://"):
            key = key[len("mem://") :]
        if key not in self._blobs:
            raise FileNotFoundError(f"blob not found: {ref}")
        return self._blobs[key]


class InMemoryVaultRepository(IVaultRepository):
    def __init__(self) -> None:
        self._collections: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}

    def _get_collection(self, collection_name: str) -> dict[str, dict[str, dict[str, Any]]]:
        if collection_name not in self._collections:
            self._collections[collection_name] = {}
        return self._collections[collection_name]

    def _get_section(self, collection_name: str, section_id: str) -> dict[str, dict[str, Any]]:
        coll = self._get_collection(collection_name)
        if section_id not in coll:
            coll[section_id] = {}
        return coll[section_id]

    def put(self, collection_name: str, documents: list[dict[str, Any]], section_id: str = "default") -> bool:
        section = self._get_section(collection_name, section_id)
        for doc in documents:
            doc_id = doc.get("id")
            if not doc_id:
                continue
            section[str(doc_id)] = doc
        return True

    def get(self, collection_name: str, doc_id: str, section_id: str = "default") -> dict[str, Any] | None:
        section = self._get_section(collection_name, section_id)
        return section.get(str(doc_id))

    def delete(self, collection_name: str, doc_id: str, section_id: str = "default") -> bool:
        section = self._get_section(collection_name, section_id)
        if str(doc_id) in section:
            del section[str(doc_id)]
            return True
        return False

    def query(self, collection_name: str, filters: dict[str, str], section_id: str = "default") -> list[dict[str, Any]]:
        section = self._get_section(collection_name, section_id)
        results = []
        for doc in section.values():
            meta = doc.get("meta", {})
            claims = meta.get("claims", {}) if isinstance(meta, dict) else {}
            
            match = True
            for k, v in filters.items():
                if claims.get(k) != v:
                    match = False
                    break
            
            if match:
                results.append(doc)
        return results
