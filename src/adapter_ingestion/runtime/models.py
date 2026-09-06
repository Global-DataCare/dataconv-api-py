# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _norm(value: str) -> str:
    return str(value or "").strip().lower()


@dataclass(frozen=True)
class ConfigKey:
    alternate_name: str
    manufacturer: str
    sector: str = ""
    manufacturer_version: str = ""
    country: str = ""
    facility_id: str = ""

    def normalized(self) -> "ConfigKey":
        return ConfigKey(
            alternate_name=_norm(self.alternate_name),
            manufacturer=_norm(self.manufacturer),
            sector=_norm(self.sector),
            manufacturer_version=_norm(self.manufacturer_version),
            country=_norm(self.country),
            facility_id=_norm(self.facility_id),
        )

    def as_token(self) -> str:
        n = self.normalized()
        return (
            f"{n.alternate_name}|{n.manufacturer}|{n.sector}|{n.manufacturer_version}|"
            f"{n.country}|{n.facility_id}"
        )


@dataclass(frozen=True)
class StoredConfig:
    key: ConfigKey
    object_id: str
    object_type: str
    content: dict[str, Any]
    revision: int = 1
    created_at: str = field(default_factory=now_iso_utc)
    updated_at: str = field(default_factory=now_iso_utc)
    audit: dict[str, Any] = field(default_factory=lambda: {"createdBy": "", "updatedBy": "", "txId": "", "txTime": ""})


@dataclass(frozen=True)
class DraftRecord:
    draft_id: str
    tenant_id: str
    sector: str = "onehealth-research"
    resource_type: str = ""
    resource_id: str = ""
    content: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso_utc)
    updated_at: str = field(default_factory=now_iso_utc)


class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class JobRequest:
    alternate_name: str
    manufacturer: str
    sector: str = "onehealth-research"
    manufacturer_version: str = ""
    country: str = ""
    facility_id: str = ""
    input_ref: str = ""
    send: bool = False
    requested_by: str = ""
    mode: str = "persistent"  # persistent | demo-ephemeral
    inline_config: dict[str, Any] = field(default_factory=dict)
    thid: str = ""
    research_study_reference: str = ""


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    thid: str
    status: str
    request: JobRequest
    config_key_used: ConfigKey | None = None
    created_at: str = field(default_factory=now_iso_utc)
    started_at: str = ""
    finished_at: str = ""
    worker_id: str = ""
    result_ref: str = ""
    error: str = ""
    delivered_at: str = ""

    @staticmethod
    def new_queued(request: JobRequest) -> "JobRecord":
        thid = str(request.thid or "").strip() or f"job-{uuid.uuid4()}"
        return JobRecord(
            job_id=str(uuid.uuid4()),
            thid=thid,
            status=JobStatus.QUEUED,
            request=request,
        )
