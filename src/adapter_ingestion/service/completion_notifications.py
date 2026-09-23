# Copyright ConnectHealth.info (Connecting Solution & Applications Ltd.)
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable
from urllib.parse import quote

from gdc_data_utils import CommunicationClaim, FHIR_API_CONTEXT

from ..gateway_client import post_didcomm_plaintext
from ..models import didcomm_plaintext_message
from ..runtime import CompletionNotificationStatus, JobRecord, JobStatus, PreconversionControlPlane
from ..runtime.models import now_iso_utc


FHIR_COMMUNICATION_RESOURCE = "Communication"
FHIR_TASK_RESOURCE = "Task"
FHIR_COMMUNICATION_CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/communication-category"
FHIR_TASK_STATUS_SYSTEM = "http://hl7.org/fhir/task-status"
FHIR_NOTIFICATION_CATEGORY = "notification"
FHIR_COMMUNICATION_COMPLETED = "completed"


@dataclass(frozen=True)
class CompletionNotificationConfig:
    enabled: bool
    gateway_base_url: str
    bearer_token: str
    audience: str
    issuer_did: str
    audience_did: str
    timeout_seconds: int = 5
    max_attempts: int = 5


@dataclass(frozen=True)
class CompletionNotificationDelivery:
    status: int
    location: str | None = None


CompletionNotificationSender = Callable[[str, str, str, dict[str, Any], int], Any]


def completion_notification_config(settings: Any) -> CompletionNotificationConfig:
    return CompletionNotificationConfig(
        enabled=bool(getattr(settings, "gw_completion_notifications_enabled", False)),
        gateway_base_url=str(getattr(settings, "gw_completion_notification_base_url", "") or "").strip(),
        bearer_token=str(getattr(settings, "gw_completion_notification_bearer_token", "") or "").strip(),
        audience=str(getattr(settings, "gw_completion_notification_audience", "") or "").strip(),
        issuer_did=str(
            getattr(settings, "gw_completion_notification_issuer_did", "")
            or getattr(settings, "default_issuer_did", "")
            or ""
        ).strip(),
        audience_did=str(
            getattr(settings, "gw_completion_notification_audience_did", "")
            or getattr(settings, "default_audience_did", "")
            or ""
        ).strip(),
        timeout_seconds=max(1, int(getattr(settings, "gw_completion_notification_timeout_seconds", 5) or 5)),
        max_attempts=max(1, int(getattr(settings, "gw_completion_notification_max_attempts", 5) or 5)),
    )


def build_terminal_job_communication(job: JobRecord, config: CompletionNotificationConfig) -> dict[str, Any]:
    if job.status not in {JobStatus.SUCCEEDED, JobStatus.FAILED}:
        raise ValueError("completion_notification_requires_terminal_job")
    recipient = str(job.request.requested_by or "").strip()
    study = str(job.request.research_study_reference or "").strip()
    if not recipient:
        raise ValueError("completion_notification_recipient_required")
    if not study:
        raise ValueError("completion_notification_research_study_required")
    task_status = "completed" if job.status == JobStatus.SUCCEEDED else "failed"
    return {
        "resourceType": FHIR_COMMUNICATION_RESOURCE,
        "id": f"job-terminal-{job.job_id}",
        "meta": {
            "claims": {
                "@context": FHIR_API_CONTEXT,
                CommunicationClaim.IDENTIFIER: str(job.thid or "").strip(),
                CommunicationClaim.STATUS: FHIR_COMMUNICATION_COMPLETED,
                CommunicationClaim.CATEGORY: (
                    f"{FHIR_COMMUNICATION_CATEGORY_SYSTEM}|{FHIR_NOTIFICATION_CATEGORY}"
                ),
                CommunicationClaim.RECIPIENT: recipient,
                CommunicationClaim.SENDER: _required(config.issuer_did, "completion_notification_issuer_required"),
                CommunicationClaim.SENT: _required(job.finished_at, "completion_notification_finished_at_required"),
                CommunicationClaim.SUBJECT: study,
                CommunicationClaim.CONTENT_REFERENCE: f"{FHIR_TASK_RESOURCE}/{job.job_id}",
                CommunicationClaim.CONTENT_CODE: f"{FHIR_TASK_STATUS_SYSTEM}|{task_status}",
            }
        },
    }


def queue_completion_notification(control_plane: PreconversionControlPlane, job_id: str) -> JobRecord:
    job = control_plane.get_job(job_id)
    if not job:
        raise KeyError(f"job not found: {job_id}")
    if job.status not in {JobStatus.SUCCEEDED, JobStatus.FAILED}:
        raise ValueError("completion_notification_requires_terminal_job")
    if job.completion_notification_status == CompletionNotificationStatus.DELIVERED:
        return job
    updated = replace(
        job,
        completion_notification_status=CompletionNotificationStatus.PENDING,
        completion_notification_error="",
    )
    control_plane.job_store.put(updated)
    return updated


def deliver_pending_completion_notifications(
    control_plane: PreconversionControlPlane,
    config: CompletionNotificationConfig,
    *,
    send: CompletionNotificationSender = post_didcomm_plaintext,
) -> str | None:
    if not config.enabled:
        return None
    candidates = sorted(
        (
            job for job in control_plane.list_jobs()
            if job.completion_notification_status
            in {CompletionNotificationStatus.PENDING, CompletionNotificationStatus.RETRYABLE}
            and job.completion_notification_attempts < max(1, int(config.max_attempts))
        ),
        key=lambda job: (str(job.finished_at or ""), str(job.job_id or "")),
    )
    if not candidates:
        return None
    job = candidates[0]
    attempts = int(job.completion_notification_attempts) + 1
    try:
        bearer_token = _resolve_bearer_token(config)
        communication = build_terminal_job_communication(job, config)
        payload = didcomm_plaintext_message(
            thid=str(job.thid or "").strip(),
            issuer_did=_required(config.issuer_did, "completion_notification_issuer_required"),
            audience_did=_required(config.audience_did, "completion_notification_audience_did_required"),
            entries=[{
                "request": {"method": "POST", "url": FHIR_COMMUNICATION_RESOURCE},
                "resource": communication,
            }],
        )
        response = send(
            config.gateway_base_url,
            _gateway_route(job),
            bearer_token,
            payload,
            max(1, int(config.timeout_seconds)),
        )
        status = int(getattr(response, "status", 0) or 0)
        if status < 200 or status >= 300:
            raise RuntimeError(f"completion_notification_gateway_status_{status}")
        updated = replace(
            job,
            completion_notification_status=CompletionNotificationStatus.DELIVERED,
            completion_notification_attempts=attempts,
            completion_notification_error="",
            completion_notification_delivered_at=now_iso_utc(),
        )
    except Exception as exc:
        terminal_failure = attempts >= max(1, int(config.max_attempts))
        updated = replace(
            job,
            completion_notification_status=(
                CompletionNotificationStatus.FAILED
                if terminal_failure
                else CompletionNotificationStatus.RETRYABLE
            ),
            completion_notification_attempts=attempts,
            completion_notification_error=str(exc),
        )
    control_plane.job_store.put(updated)
    return job.job_id


def _gateway_route(job: JobRecord) -> str:
    tenant = _path_segment(job.request.alternate_name, "completion_notification_tenant_required")
    jurisdiction = _path_segment(job.request.country, "completion_notification_jurisdiction_required")
    sector = _path_segment(job.request.sector, "completion_notification_sector_required")
    return (
        f"/{tenant}/cds-{jurisdiction}/v1/{sector}/digitaltwin/"
        f"{FHIR_API_CONTEXT}/{FHIR_COMMUNICATION_RESOURCE}/_batch"
    )


def _resolve_bearer_token(config: CompletionNotificationConfig) -> str:
    direct = str(config.bearer_token or "").strip()
    if direct:
        return direct
    audience = str(config.audience or "").strip()
    if not audience:
        raise ValueError("completion_notification_auth_required")
    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from google.oauth2.id_token import fetch_id_token
    except ImportError as exc:  # pragma: no cover - production dependency gate
        raise RuntimeError("google-auth is required for gateway workload identity") from exc
    return _required(
        str(fetch_id_token(GoogleAuthRequest(), audience) or ""),
        "completion_notification_identity_token_missing",
    )


def _path_segment(value: str, error: str) -> str:
    return quote(_required(value, error), safe="")


def _required(value: str, error: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(error)
    return text
