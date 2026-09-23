# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.
from __future__ import annotations

from dataclasses import replace

from gdc_data_utils import CommunicationClaim, FHIR_API_CONTEXT

from adapter_ingestion.runtime import JobRequest, JobStatus, PreconversionControlPlane
from adapter_ingestion.runtime.adapters import InMemoryConfigStore, InMemoryJobQueue, InMemoryJobStore
from adapter_ingestion.service.completion_notifications import (
    CompletionNotificationConfig,
    CompletionNotificationDelivery,
    build_terminal_job_communication,
    deliver_pending_completion_notifications,
    queue_completion_notification,
)


EXAMPLE = {
    "tenant": "research-tenant",
    "sector": "onehealth-research",
    "jurisdiction": "CA-BC",
    "requester": "did:web:professional.example:employee:reviewer",
    "sender": "did:web:dataconv.example:service:worker",
    "audience": "did:web:gw.example",
    "thread": "research-conversion-1",
    "study": "ResearchStudy/study-1",
    "finished": "2026-09-23T18:00:00Z",
    "gateway": "https://gateway.example.test",
    "token": "gateway-token",
}


def _control_plane() -> PreconversionControlPlane:
    return PreconversionControlPlane(
        config_store=InMemoryConfigStore(),
        job_store=InMemoryJobStore(),
        job_queue=InMemoryJobQueue(),
    )


def _terminal_job(status: str = JobStatus.SUCCEEDED):
    queued = _control_plane().submit_job(JobRequest(
        alternate_name=EXAMPLE["tenant"],
        manufacturer="source-system",
        sector=EXAMPLE["sector"],
        country=EXAMPLE["jurisdiction"],
        requested_by=EXAMPLE["requester"],
        thid=EXAMPLE["thread"],
        research_study_reference=EXAMPLE["study"],
    ))
    return replace(queued, status=status, finished_at=EXAMPLE["finished"])


def _config() -> CompletionNotificationConfig:
    return CompletionNotificationConfig(
        enabled=True,
        gateway_base_url=EXAMPLE["gateway"],
        bearer_token=EXAMPLE["token"],
        audience="",
        issuer_did=EXAMPLE["sender"],
        audience_did=EXAMPLE["audience"],
        timeout_seconds=5,
        max_attempts=3,
    )


def test_builds_claims_first_terminal_communication_without_nested_fhir_state() -> None:
    job = _terminal_job()

    communication = build_terminal_job_communication(job, _config())
    claims = communication["meta"]["claims"]

    assert communication == {
        "resourceType": "Communication",
        "id": f"job-terminal-{job.job_id}",
        "meta": {"claims": {
            "@context": FHIR_API_CONTEXT,
            CommunicationClaim.IDENTIFIER: job.thid,
            CommunicationClaim.STATUS: "completed",
            CommunicationClaim.CATEGORY: "http://terminology.hl7.org/CodeSystem/communication-category|notification",
            CommunicationClaim.RECIPIENT: EXAMPLE["requester"],
            CommunicationClaim.SENDER: EXAMPLE["sender"],
            CommunicationClaim.SENT: EXAMPLE["finished"],
            CommunicationClaim.SUBJECT: EXAMPLE["study"],
            CommunicationClaim.CONTENT_REFERENCE: f"Task/{job.job_id}",
            CommunicationClaim.CONTENT_CODE: "http://hl7.org/fhir/task-status|completed",
        }},
    }
    assert "status" not in communication
    assert claims[CommunicationClaim.CONTENT_CODE].endswith("|completed")


def test_delivers_pending_notification_to_gateway_and_persists_delivery_state() -> None:
    control = _control_plane()
    queued = control.submit_job(_terminal_job().request)
    terminal = replace(queued, status=JobStatus.SUCCEEDED, finished_at=EXAMPLE["finished"])
    control.job_store.put(terminal)
    queue_completion_notification(control, terminal.job_id)
    calls: list[tuple[str, str, str, dict]] = []

    def send(base_url: str, route_path: str, bearer_token: str, payload: dict, timeout_seconds: int):
        calls.append((base_url, route_path, bearer_token, payload))
        return CompletionNotificationDelivery(status=202, location="/response")

    delivered = deliver_pending_completion_notifications(control, _config(), send=send)

    assert delivered == terminal.job_id
    assert calls[0][0] == EXAMPLE["gateway"]
    assert calls[0][1] == (
        f"/{EXAMPLE['tenant']}/cds-{EXAMPLE['jurisdiction']}/v1/{EXAMPLE['sector']}"
        "/digitaltwin/org.hl7.fhir.api/Communication/_batch"
    )
    assert calls[0][2] == EXAMPLE["token"]
    assert calls[0][3]["thid"] == terminal.thid
    assert calls[0][3]["body"]["data"][0]["resource"]["meta"]["claims"][CommunicationClaim.RECIPIENT] == EXAMPLE["requester"]
    persisted = control.get_job(terminal.job_id)
    assert persisted is not None
    assert persisted.completion_notification_status == "delivered"
    assert persisted.completion_notification_attempts == 1
    assert persisted.completion_notification_delivered_at


def test_failed_delivery_is_retryable_without_changing_the_terminal_job_result() -> None:
    control = _control_plane()
    queued = control.submit_job(_terminal_job(JobStatus.FAILED).request)
    terminal = replace(queued, status=JobStatus.FAILED, finished_at=EXAMPLE["finished"], error="invalid workbook")
    control.job_store.put(terminal)
    queue_completion_notification(control, terminal.job_id)

    def fail(*_args, **_kwargs):
        raise RuntimeError("gateway unavailable")

    attempted = deliver_pending_completion_notifications(control, _config(), send=fail)

    assert attempted == terminal.job_id
    persisted = control.get_job(terminal.job_id)
    assert persisted is not None
    assert persisted.status == JobStatus.FAILED
    assert persisted.error == terminal.error
    assert persisted.completion_notification_status == "retryable"
    assert persisted.completion_notification_attempts == 1
    assert persisted.completion_notification_error == "gateway unavailable"
