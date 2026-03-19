# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from .models import ConfigKey, JobRecord, JobRequest, JobStatus, StoredConfig, now_iso_utc
from .ports import ConfigStore, JobQueue, JobStore
from .resolution import resolution_candidates


def _parse_iso_utc(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class PreconversionControlPlane:
    def __init__(self, config_store: ConfigStore, job_store: JobStore, job_queue: JobQueue) -> None:
        self.config_store = config_store
        self.job_store = job_store
        self.job_queue = job_queue

    def upsert_config(
        self,
        key: ConfigKey,
        content: dict,
        updated_by: str = "",
        audit: dict[str, Any] | None = None,
    ) -> StoredConfig:
        normalized = key.normalized()
        current = self.config_store.get(normalized)
        revision = (current.revision + 1) if current else 1
        actor = str(updated_by or "").strip()
        created_at = str(current.created_at).strip() if current else now_iso_utc()
        audit_payload: dict[str, Any] = {"createdBy": "", "updatedBy": "", "txId": "", "txTime": ""}
        if current and isinstance(current.audit, dict):
            audit_payload.update(
                {k: current.audit.get(k, "") for k in ("createdBy", "updatedBy", "txId", "txTime")}
            )
        if not str(audit_payload.get("createdBy", "")).strip():
            audit_payload["createdBy"] = actor
        audit_payload["updatedBy"] = actor
        if isinstance(audit, dict):
            if "txId" in audit:
                audit_payload["txId"] = str(audit.get("txId", "") or "")
            if "txTime" in audit:
                audit_payload["txTime"] = str(audit.get("txTime", "") or "")
        object_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"preconv-config|{normalized.as_token()}"))
        stored = StoredConfig(
            key=normalized,
            object_id=object_id,
            object_type="tenant-adapter-config",
            content=dict(content or {}),
            revision=revision,
            created_at=created_at,
            updated_at=now_iso_utc(),
            audit=audit_payload,
        )
        return self.config_store.put(stored)

    def resolve_config(self, selector: ConfigKey) -> StoredConfig | None:
        for candidate in resolution_candidates(selector):
            found = self.config_store.get(candidate)
            if found:
                return found
        return None

    def submit_job(self, request: JobRequest) -> JobRecord:
        queued = JobRecord.new_queued(request=request)
        self.job_store.put(queued)
        self.job_queue.enqueue(queued.job_id)
        return queued

    def get_job(self, job_id: str) -> JobRecord | None:
        return self.job_store.get(job_id)

    def get_job_by_thid(self, thid: str) -> JobRecord | None:
        return self.job_store.find_by_thid(thid)

    def delete_job(self, job_id: str) -> bool:
        return self.job_store.delete(job_id)

    def list_jobs(self) -> list[JobRecord]:
        return self.job_store.list()

    def get_queue_position(self, job_id: str) -> int | None:
        token = str(job_id or "").strip()
        if not token:
            return None
        queued_jobs = [job for job in self.list_jobs() if str(job.status or "").strip().lower() == JobStatus.QUEUED]
        if not queued_jobs:
            return None

        def _sort_key(job: JobRecord) -> tuple[str, str]:
            created_at = str(job.created_at or "").strip()
            return (created_at, str(job.job_id or "").strip())

        for index, job in enumerate(sorted(queued_jobs, key=_sort_key), start=1):
            if str(job.job_id or "").strip() == token:
                return index
        return None

    def cleanup_expired_jobs(
        self,
        *,
        ttl_seconds: int,
        dry_run: bool = False,
        limit: int = 0,
        include_details: bool = False,
    ) -> dict[str, Any]:
        scanned = 0
        terminal = 0
        expired = 0
        deleted = 0
        details: list[dict[str, Any]] = []

        if ttl_seconds < 0:
            report = {
                "scanned": scanned,
                "terminal": terminal,
                "expired": expired,
                "deleted": deleted,
            }
            if include_details:
                report["details"] = details
            return report

        now_dt = datetime.now(timezone.utc)
        expiration_delta = timedelta(seconds=max(0, int(ttl_seconds)))
        max_delete = max(0, int(limit))

        for job in self.list_jobs():
            scanned += 1
            status = str(job.status or "").strip().lower()
            if status not in {JobStatus.SUCCEEDED, JobStatus.FAILED}:
                continue
            terminal += 1

            base_ts = str(job.finished_at or job.created_at).strip()
            base_dt = _parse_iso_utc(base_ts)
            if base_dt is None:
                continue
            if now_dt < (base_dt + expiration_delta):
                continue
            expired += 1
            detail = {
                "jobId": job.job_id,
                "thid": job.thid,
                "tenantId": job.request.alternate_name,
                "manufacturer": job.request.manufacturer,
                "manufacturerVersion": job.request.manufacturer_version,
                "country": job.request.country,
                "status": job.status,
                "createdAt": job.created_at,
                "finishedAt": job.finished_at,
                "deliveredAt": job.delivered_at,
                "delivered": bool(str(job.delivered_at or "").strip()),
                "deleted": False,
                "reason": "expired",
            }

            if dry_run:
                if include_details:
                    details.append(detail)
                continue
            if max_delete and deleted >= max_delete:
                if include_details:
                    details.append(detail)
                continue
            if self.delete_job(job.job_id):
                deleted += 1
                detail["deleted"] = True
            if include_details:
                details.append(detail)

        report = {
            "scanned": scanned,
            "terminal": terminal,
            "expired": expired,
            "deleted": deleted,
        }
        if include_details:
            report["details"] = details
        return report

    def claim_next_job(self, worker_id: str) -> JobRecord | None:
        while True:
            job_id = self.job_queue.dequeue()
            if not job_id:
                return None
            job = self.job_store.get(job_id)
            if not job:
                continue
            if job.status != JobStatus.QUEUED:
                continue

            selector = ConfigKey(
                alternate_name=job.request.alternate_name,
                manufacturer=job.request.manufacturer,
                sector=job.request.sector,
                manufacturer_version=job.request.manufacturer_version,
                country=job.request.country,
                facility_id=job.request.facility_id,
            )
            config = self.resolve_config(selector)
            running = replace(
                job,
                status=JobStatus.RUNNING,
                started_at=now_iso_utc(),
                worker_id=str(worker_id or "").strip(),
                config_key_used=config.key if config else None,
            )
            self.job_store.put(running)
            return running

    def mark_job_succeeded(self, job_id: str, result_ref: str = "") -> JobRecord:
        job = self.job_store.get(job_id)
        if not job:
            raise KeyError(f"job not found: {job_id}")
        updated = replace(
            job,
            status=JobStatus.SUCCEEDED,
            finished_at=now_iso_utc(),
            result_ref=str(result_ref or "").strip(),
            error="",
        )
        self.job_store.put(updated)
        return updated

    def mark_job_failed(self, job_id: str, error: str) -> JobRecord:
        job = self.job_store.get(job_id)
        if not job:
            raise KeyError(f"job not found: {job_id}")
        updated = replace(
            job,
            status=JobStatus.FAILED,
            finished_at=now_iso_utc(),
            error=str(error or "").strip(),
        )
        self.job_store.put(updated)
        return updated

    def mark_job_delivered(self, job_id: str) -> JobRecord:
        job = self.job_store.get(job_id)
        if not job:
            raise KeyError(f"job not found: {job_id}")
        if str(job.delivered_at or "").strip():
            return job
        updated = replace(job, delivered_at=now_iso_utc())
        self.job_store.put(updated)
        return updated
