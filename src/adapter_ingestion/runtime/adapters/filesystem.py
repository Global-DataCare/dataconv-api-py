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


def _safe_token(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "_"
    return re.sub(r"[^a-z0-9._-]+", "_", text)


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


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


class FileSystemVaultRepository(IVaultRepository):
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.base_dir = self.root_dir / "vaults"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path_for_doc(self, collection_name: str, section_id: str, doc_id: str) -> Path:
        return self.base_dir / _safe_token(collection_name) / _safe_token(section_id) / "org.hl7.fhir.api" / f"{_safe_token(doc_id)}.json"

    def put(self, collection_name: str, documents: list[dict[str, Any]], section_id: str = "default") -> bool:
        if not documents:
            return True
        for doc in documents:
            doc_id = doc.get("id")
            if not doc_id:
                continue
            path = self._path_for_doc(collection_name, section_id, str(doc_id))
            _write_json(path, doc)
        return True

    def get(self, collection_name: str, doc_id: str, section_id: str = "default") -> dict[str, Any] | None:
        path = self._path_for_doc(collection_name, section_id, doc_id)
        return _read_json(path)

    def delete(self, collection_name: str, doc_id: str, section_id: str = "default") -> bool:
        path = self._path_for_doc(collection_name, section_id, doc_id)
        if not path.exists():
            return False
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False

    def query(self, collection_name: str, filters: dict[str, str], section_id: str = "default") -> list[dict[str, Any]]:
        base = self.base_dir / _safe_token(collection_name) / _safe_token(section_id) / "org.hl7.fhir.api"
        if not base.exists():
            return []
            
        results = []
        for path in base.glob("*.json"):
            doc = _read_json(path)
            if not doc:
                continue
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
