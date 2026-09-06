# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re
import uuid

from ..models import ConfigKey, JobRecord, JobRequest, StoredConfig
from ..ports import BlobStore, ConfigStore, IVaultRepository, JobQueue, JobStore
from ...subject_links import ProtectedSubjectLinkRecord


def _is_pubsub_deadline_exceeded(exc: Exception) -> bool:
    if exc.__class__.__name__ == "DeadlineExceeded":
        return True
    try:
        from google.api_core import exceptions as google_exceptions
    except ImportError:
        return False
    return isinstance(exc, google_exceptions.DeadlineExceeded)


def _safe_token(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "_"
    return re.sub(r"[^a-z0-9._-]+", "_", text)


def _config_to_dict(config: StoredConfig) -> dict[str, Any]:
    return {
        "id": config.object_id,
        "type": config.object_type,
        "key": {
            "alternateName": config.key.alternate_name,
            "manufacturer": config.key.manufacturer,
            "sector": config.key.sector,
            "manufacturerVersion": config.key.manufacturer_version,
            "country": config.key.country,
            "facilityId": config.key.facility_id,
        },
        "content": config.content,
        "revision": config.revision,
        "createdAt": config.created_at,
        "updatedAt": config.updated_at,
        "audit": config.audit,
    }


def _dict_to_config(data: dict[str, Any]) -> StoredConfig:
    key_raw = data.get("key", {}) if isinstance(data.get("key"), dict) else {}
    normalized_key = ConfigKey(
        alternate_name=str(key_raw.get("alternateName", "")),
        manufacturer=str(key_raw.get("manufacturer", "")),
        sector=str(key_raw.get("sector", "")),
        manufacturer_version=str(key_raw.get("manufacturerVersion", "")),
        country=str(key_raw.get("country", "")),
        facility_id=str(key_raw.get("facilityId", "")),
    ).normalized()
    fallback_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"preconv-config|{normalized_key.as_token()}"))
    audit = data.get("audit", {}) if isinstance(data.get("audit"), dict) else {}
    normalized_audit = {
        "createdBy": str(audit.get("createdBy", "") or ""),
        "updatedBy": str(audit.get("updatedBy", "") or ""),
        "txId": str(audit.get("txId", "") or ""),
        "txTime": str(audit.get("txTime", "") or ""),
    }
    return StoredConfig(
        key=normalized_key,
        object_id=str(data.get("id", "")) or fallback_id,
        object_type=str(data.get("type", "")) or "tenant-adapter-config",
        content=data.get("content", {}) if isinstance(data.get("content"), dict) else {},
        revision=int(data.get("revision", 1) or 1),
        created_at=str(data.get("createdAt", "")),
        updated_at=str(data.get("updatedAt", "")),
        audit=normalized_audit,
    )


def _job_to_dict(job: JobRecord) -> dict[str, Any]:
    req = job.request
    return {
        "jobId": job.job_id,
        "thid": job.thid,
        "status": job.status,
        "request": {
            "alternateName": req.alternate_name,
            "manufacturer": req.manufacturer,
            "sector": req.sector,
            "manufacturerVersion": req.manufacturer_version,
            "country": req.country,
            "facilityId": req.facility_id,
            "inputRef": req.input_ref,
            "send": req.send,
            "requestedBy": req.requested_by,
            "mode": req.mode,
            "inlineConfig": req.inline_config,
            "thid": req.thid,
            "researchStudyReference": req.research_study_reference,
        },
        "configKeyUsed": {
            "alternateName": job.config_key_used.alternate_name,
            "manufacturer": job.config_key_used.manufacturer,
            "sector": job.config_key_used.sector,
            "manufacturerVersion": job.config_key_used.manufacturer_version,
            "country": job.config_key_used.country,
            "facilityId": job.config_key_used.facility_id,
        }
        if job.config_key_used
        else None,
        "createdAt": job.created_at,
        "startedAt": job.started_at,
        "finishedAt": job.finished_at,
        "workerId": job.worker_id,
        "resultRef": job.result_ref,
        "error": job.error,
        "deliveredAt": job.delivered_at,
    }


def _dict_to_job(data: dict[str, Any]) -> JobRecord:
    req_raw = data.get("request", {}) if isinstance(data.get("request"), dict) else {}
    key_raw = data.get("configKeyUsed", {}) if isinstance(data.get("configKeyUsed"), dict) else {}
    config_key = None
    if key_raw:
        config_key = ConfigKey(
            alternate_name=str(key_raw.get("alternateName", "")),
            manufacturer=str(key_raw.get("manufacturer", "")),
            sector=str(key_raw.get("sector", "")),
            manufacturer_version=str(key_raw.get("manufacturerVersion", "")),
            country=str(key_raw.get("country", "")),
            facility_id=str(key_raw.get("facilityId", "")),
        ).normalized()
    request = JobRequest(
        alternate_name=str(req_raw.get("alternateName", "")),
        manufacturer=str(req_raw.get("manufacturer", "")),
        sector=str(req_raw.get("sector", "onehealth-research")),
        manufacturer_version=str(req_raw.get("manufacturerVersion", "")),
        country=str(req_raw.get("country", "")),
        facility_id=str(req_raw.get("facilityId", "")),
        input_ref=str(req_raw.get("inputRef", "")),
        send=bool(req_raw.get("send", False)),
        requested_by=str(req_raw.get("requestedBy", "")),
        mode=str(req_raw.get("mode", "persistent")),
        inline_config=req_raw.get("inlineConfig", {}) if isinstance(req_raw.get("inlineConfig"), dict) else {},
        thid=str(req_raw.get("thid", "")),
        research_study_reference=str(req_raw.get("researchStudyReference", "")),
    )
    return JobRecord(
        job_id=str(data.get("jobId", "")),
        thid=str(data.get("thid", "")),
        status=str(data.get("status", "")),
        request=request,
        config_key_used=config_key,
        created_at=str(data.get("createdAt", "")),
        started_at=str(data.get("startedAt", "")),
        finished_at=str(data.get("finishedAt", "")),
        worker_id=str(data.get("workerId", "")),
        result_ref=str(data.get("resultRef", "")),
        error=str(data.get("error", "")),
        delivered_at=str(data.get("deliveredAt", "")),
    )


class FirestoreVaultRepository(IVaultRepository):
    def __init__(self, project_id: str) -> None:
        try:
            from google.cloud import firestore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Missing dependency google-cloud-firestore. Install with: "
                "pip install 'adapter-ingestion-py[gcp]'"
            ) from exc

        self._client = firestore.Client(project=project_id or None)
        
    def _docs_ref(self, collection_name: str, section_id: str) -> "google.cloud.firestore.CollectionReference":
        # Follows the {collection_name}/{section_id}/org.hl7.fhir.api pattern
        return self._client.collection(collection_name).document(str(section_id or "default")).collection("org.hl7.fhir.api")

    def put(self, collection_name: str, documents: list[dict[str, Any]], section_id: str = "default") -> bool:
        if not documents:
            return True
        try:
            batch = self._client.batch()
            docs_ref = self._docs_ref(collection_name, section_id)
            for doc in documents:
                doc_id = doc.get("id")
                if not doc_id:
                    continue  # We only save records with known IDs
                doc_ref = docs_ref.document(_safe_token(str(doc_id)))
                batch.set(doc_ref, doc)
            batch.commit()
            return True
        except Exception as exc:
            import logging
            logging.error("FirestoreVaultRepository 'put' failed: %s", exc)
            return False

    def get(self, collection_name: str, doc_id: str, section_id: str = "default") -> dict[str, Any] | None:
        doc_ref = self._docs_ref(collection_name, section_id).document(_safe_token(doc_id))
        snap = doc_ref.get()
        if not snap.exists:
            return None
        return snap.to_dict()

    def delete(self, collection_name: str, doc_id: str, section_id: str = "default") -> bool:
        try:
            doc_ref = self._docs_ref(collection_name, section_id).document(_safe_token(doc_id))
            doc_ref.delete()
            return True
        except Exception:
            return False

    def query(self, collection_name: str, filters: dict[str, str], section_id: str = "default") -> list[dict[str, Any]]:
        try:
            results = []
            for doc_snap in self._docs_ref(collection_name, section_id).stream():
                data = doc_snap.to_dict() or {}
                claims = ((data.get("meta") or {}).get("claims") or {})
                if not isinstance(claims, dict):
                    continue
                matched = True
                for k, v in filters.items():
                    if str(claims.get(str(k), "") or "") != str(v):
                        matched = False
                        break
                if matched:
                    results.append(data)
            return results
        except Exception as exc:
            import logging
            logging.error("FirestoreVaultRepository 'query' failed: %s", exc)
            return []


class FirestoreSubjectLinkRecordStore:
    """Dedicated confidential store for encrypted external-id to twin UUID links."""

    def __init__(self, *, project_id: str, collection: str) -> None:
        try:
            from google.cloud import firestore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Missing dependency google-cloud-firestore. Install with: "
                "pip install 'adapter-ingestion-py[gcp]'"
            ) from exc

        self._client = firestore.Client(project=project_id or None)
        self._collection = str(collection or "preconversion-subject-links")

    @staticmethod
    def _from_dict(record_id: str, payload: dict[str, Any]) -> ProtectedSubjectLinkRecord:
        return ProtectedSubjectLinkRecord(
            id=record_id,
            nonce_base64url=str(payload.get("nonceBase64url", "")),
            ciphertext_base64url=str(payload.get("ciphertextBase64url", "")),
            key_version=str(payload.get("keyVersion", "v1")),
        )

    def get(self, record_id: str) -> ProtectedSubjectLinkRecord | None:
        snap = self._client.collection(self._collection).document(_safe_token(record_id)).get()
        if not snap.exists:
            return None
        payload = snap.to_dict()
        return self._from_dict(record_id, payload) if isinstance(payload, dict) else None

    def create_if_absent(self, record: ProtectedSubjectLinkRecord) -> ProtectedSubjectLinkRecord:
        from google.api_core.exceptions import AlreadyExists

        doc_ref = self._client.collection(self._collection).document(_safe_token(record.id))
        try:
            doc_ref.create(
                {
                    "nonceBase64url": record.nonce_base64url,
                    "ciphertextBase64url": record.ciphertext_base64url,
                    "keyVersion": record.key_version,
                }
            )
            return record
        except AlreadyExists:
            existing = self.get(record.id)
            if existing is None:  # pragma: no cover - defensive race guard
                raise RuntimeError("subject link disappeared after concurrent create")
            return existing


class FirestoreConfigStore(ConfigStore):
    def __init__(self, *, project_id: str, collection: str) -> None:
        try:
            from google.cloud import firestore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Missing dependency google-cloud-firestore. Install with: "
                "pip install 'adapter-ingestion-py[gcp]'"
            ) from exc

        self._client = firestore.Client(project=project_id or None)
        self._collection = str(collection or "preconversion-configs")

    def put(self, config: StoredConfig) -> StoredConfig:
        self._client.collection(self._collection).document(_safe_token(config.key.as_token())).set(_config_to_dict(config))
        return config

    def get(self, key: ConfigKey) -> StoredConfig | None:
        snap = self._client.collection(self._collection).document(_safe_token(key.as_token())).get()
        if not snap.exists:
            return None
        payload = snap.to_dict()
        return _dict_to_config(payload) if isinstance(payload, dict) else None


class FirestoreJobStore(JobStore):
    def __init__(self, *, project_id: str, collection: str) -> None:
        try:
            from google.cloud import firestore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Missing dependency google-cloud-firestore. Install with: "
                "pip install 'adapter-ingestion-py[gcp]'"
            ) from exc

        self._client = firestore.Client(project=project_id or None)
        self._collection = str(collection or "preconversion-jobs")

    def put(self, job: JobRecord) -> JobRecord:
        self._client.collection(self._collection).document(_safe_token(job.job_id)).set(_job_to_dict(job))
        return job

    def get(self, job_id: str) -> JobRecord | None:
        snap = self._client.collection(self._collection).document(_safe_token(job_id)).get()
        if not snap.exists:
            return None
        payload = snap.to_dict()
        return _dict_to_job(payload) if isinstance(payload, dict) else None

    def find_by_thid(self, thid: str) -> JobRecord | None:
        token = str(thid or "").strip()
        if not token:
            return None
        query = self._client.collection(self._collection).where("thid", "==", token).limit(1)
        for snap in query.stream():
            payload = snap.to_dict()
            if isinstance(payload, dict):
                return _dict_to_job(payload)
        return None

    def delete(self, job_id: str) -> bool:
        try:
            self._client.collection(self._collection).document(_safe_token(job_id)).delete()
            return True
        except Exception:
            return False

    def list(self) -> list[JobRecord]:
        items: list[JobRecord] = []
        for snap in self._client.collection(self._collection).stream():
            payload = snap.to_dict()
            if isinstance(payload, dict):
                items.append(_dict_to_job(payload))
        return items


class PubSubJobQueue(JobQueue):
    """
    Pull-based queue for worker deployments in Kubernetes.
    Requires both topic and subscription to exist.
    """

    def __init__(
        self,
        *,
        project_id: str,
        topic_id: str,
        subscription_id: str,
    ) -> None:
        try:
            from google.cloud import pubsub_v1
        except ImportError as exc:  # pragma: no cover - depends on optional extras
            raise RuntimeError(
                "Missing dependency google-cloud-pubsub. Install with: "
                "pip install 'adapter-ingestion-py[gcp]'"
            ) from exc

        self._publisher = pubsub_v1.PublisherClient()
        self._subscriber = pubsub_v1.SubscriberClient()
        self._topic_path = self._publisher.topic_path(project_id, topic_id)
        self._subscription_path = self._subscriber.subscription_path(project_id, subscription_id)

    def enqueue(self, job_id: str) -> None:
        self._publisher.publish(self._topic_path, str(job_id).encode("utf-8")).result(timeout=15)

    def dequeue(self) -> str | None:
        try:
            response = self._subscriber.pull(
                request={
                    "subscription": self._subscription_path,
                    "max_messages": 1,
                },
                timeout=5,
            )
        except Exception as exc:
            # Empty pull windows on Pub/Sub can surface as DeadlineExceeded.
            if _is_pubsub_deadline_exceeded(exc):
                return None
            raise
        if not response.received_messages:
            return None
        msg = response.received_messages[0]
        ack_id = msg.ack_id
        job_id = msg.message.data.decode("utf-8").strip()
        self._subscriber.acknowledge(
            request={"subscription": self._subscription_path, "ack_ids": [ack_id]}
        )
        return job_id or None


class GCSBlobStore(BlobStore):
    def __init__(self, project_id: str, bucket_name: str, prefix: str = "preconversion") -> None:
        try:
            from google.cloud import storage
        except ImportError as exc:  # pragma: no cover - depends on optional extras
            raise RuntimeError(
                "Missing dependency google-cloud-storage. Install with: "
                "pip install 'adapter-ingestion-py[gcp]'"
            ) from exc

        self._client = storage.Client(project=project_id or None)
        self._bucket = self._client.bucket(bucket_name)
        self._prefix = str(prefix or "").strip().strip("/")

    def _blob_name(self, path: str) -> str:
        clean = str(path or "").strip().lstrip("/")
        if clean.startswith("gs://"):
            # Allow idempotent writes with fully-qualified ref.
            parts = clean[5:].split("/", 1)
            if len(parts) == 2:
                return parts[1]
            return ""
        if self._prefix:
            return f"{self._prefix}/{clean}"
        return clean

    def put_bytes(
        self,
        *,
        path: str,
        payload: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        name = self._blob_name(path)
        if not name:
            raise ValueError("invalid blob path")
        blob = self._bucket.blob(name)
        blob.upload_from_string(payload, content_type=content_type)
        return f"gs://{self._bucket.name}/{name}"

    def get_bytes(self, ref: str) -> bytes:
        text = str(ref or "").strip()
        if text.startswith("gs://"):
            no_scheme = text[5:]
            parts = no_scheme.split("/", 1)
            if len(parts) != 2:
                raise ValueError(f"invalid gs:// ref: {ref}")
            bucket_name, object_name = parts[0], parts[1]
            bucket = self._client.bucket(bucket_name)
            blob = bucket.blob(object_name)
            return blob.download_as_bytes()

        # Relative refs are resolved against this bucket/prefix.
        name = self._blob_name(text)
        blob = self._bucket.blob(name)
        return blob.download_as_bytes()
