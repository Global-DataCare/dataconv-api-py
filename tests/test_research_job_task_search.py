# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from gdc_data_utils import FHIR_API_CONTEXT, TaskClaim

from adapter_ingestion.runtime import JobRequest, JobStatus, PreconversionControlPlane
from adapter_ingestion.runtime.adapters import (
    InMemoryBlobStore,
    InMemoryConfigStore,
    InMemoryJobQueue,
    InMemoryJobStore,
    InMemorySearchRepository,
    InMemoryVaultRepository,
)
from adapter_ingestion.service.managers.conversion_job_search import (
    ConversionJobSearchManager,
    project_job_as_task,
)
from adapter_ingestion.service.managers.dependencies import ApiManagerDependencies


STUDY = "ResearchStudy/study-job-search"
TENANT = "research-tenant"


def _control_plane() -> PreconversionControlPlane:
    return PreconversionControlPlane(
        config_store=InMemoryConfigStore(),
        job_store=InMemoryJobStore(),
        job_queue=InMemoryJobQueue(),
    )


def _request(*, thid: str, tenant: str = TENANT, study: str = STUDY) -> JobRequest:
    return JobRequest(
        alternate_name=tenant,
        manufacturer="source-system",
        sector="onehealth-research",
        country="CA-BC",
        requested_by="did:web:professional.example:employee:reviewer",
        thid=thid,
        research_study_reference=study,
    )


def test_projects_job_lifecycle_as_canonical_flat_task_claims() -> None:
    control = _control_plane()
    queued = control.submit_job(_request(thid="research-conversion-1"))

    task = project_job_as_task(queued)
    claims = task["meta"]["claims"]

    assert task["resourceType"] == "Task"
    assert task["id"] == queued.job_id
    assert claims == {
        "@context": FHIR_API_CONTEXT,
        TaskClaim.IDENTIFIER: queued.job_id,
        TaskClaim.GROUP_IDENTIFIER: queued.thid,
        TaskClaim.STATUS: "ready",
        TaskClaim.BUSINESS_STATUS: JobStatus.QUEUED,
        TaskClaim.INTENT: "order",
        TaskClaim.CODE: "source-system",
        TaskClaim.FOR: STUDY,
        TaskClaim.REQUESTER: queued.request.requested_by,
        TaskClaim.AUTHORED_ON: queued.created_at,
        TaskClaim.LAST_MODIFIED: queued.created_at,
    }

    assert project_job_as_task(replace(queued, status=JobStatus.RUNNING))["meta"]["claims"][TaskClaim.STATUS] == "in-progress"
    assert project_job_as_task(replace(queued, status=JobStatus.SUCCEEDED))["meta"]["claims"][TaskClaim.STATUS] == "completed"
    assert project_job_as_task(replace(queued, status=JobStatus.FAILED))["meta"]["claims"][TaskClaim.STATUS] == "failed"


def test_projects_terminal_result_or_failure_without_hiding_diagnostics() -> None:
    queued = _control_plane().submit_job(_request(thid="research-conversion-2"))
    succeeded = replace(
        queued,
        status=JobStatus.SUCCEEDED,
        started_at="2026-09-19T10:00:00Z",
        finished_at="2026-09-19T10:01:00Z",
        result_ref="mem://results/research-conversion-2.json",
    )
    failed = replace(
        succeeded,
        status=JobStatus.FAILED,
        result_ref="",
        error="Workbook has no supported rows",
    )

    completed_claims = project_job_as_task(succeeded)["meta"]["claims"]
    failed_claims = project_job_as_task(failed)["meta"]["claims"]

    assert completed_claims[TaskClaim.EXECUTION_PERIOD_START] == succeeded.started_at
    assert completed_claims[TaskClaim.EXECUTION_PERIOD_END] == succeeded.finished_at
    assert completed_claims[TaskClaim.OUTPUT_VALUE_REFERENCE] == succeeded.result_ref
    assert failed_claims[TaskClaim.STATUS_REASON] == failed.error


def test_lists_only_jobs_for_the_authorized_study_and_tenant_as_searchset() -> None:
    control = _control_plane()
    first = control.submit_job(_request(thid="research-conversion-1"))
    second = control.submit_job(_request(thid="research-conversion-2"))
    control.submit_job(_request(thid="other-tenant", tenant="another-tenant"))
    control.submit_job(_request(thid="other-study", study="ResearchStudy/other"))
    deps = ApiManagerDependencies(
        settings=SimpleNamespace(demo_mode=False, supported_jurisdictions=("*",), supported_sectors=("*",)),
        control_plane=control,
        blob_store=InMemoryBlobStore(),
        vault_repo=InMemoryVaultRepository(),
        search_repo=InMemorySearchRepository(),
        config_create_responses={},
    )
    manager = ConversionJobSearchManager(deps)
    request = SimpleNamespace(headers={"authorization": "Bearer study-token"}, query_params={})
    body = {
        "resourceType": "Parameters",
        "parameter": [
            {"name": "study", "valueReference": {"reference": STUDY}},
            {"name": "_count", "valueInteger": 1},
            {"name": "_offset", "valueInteger": 1},
        ],
    }

    with patch(
        "adapter_ingestion.service.managers.conversion_job_search._enforce_auth_context"
    ) as enforce:
        bundle = manager.handle(
            tenant_id=TENANT,
            jurisdiction="CA-BC",
            sector="onehealth-research",
            request=request,
            body=body,
        )

    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "searchset"
    assert bundle["total"] == 2
    assert len(bundle["entry"]) == 1
    assert bundle["entry"][0]["resource"]["id"] in {first.job_id, second.job_id}
    assert first.job_id != second.job_id
    enforce.assert_called_once()
    assert enforce.call_args.kwargs["required_scopes"] == {"dataconv.read"}
    assert enforce.call_args.kwargs["expected_organization"] == TENANT
    assert enforce.call_args.kwargs["expected_research_study"] == STUDY
    assert enforce.call_args.kwargs["require_study_research"] is True


@pytest.mark.parametrize("count", [0, 101])
def test_rejects_job_page_sizes_outside_one_to_one_hundred(count: int) -> None:
    deps = ApiManagerDependencies(
        settings=SimpleNamespace(demo_mode=True, supported_jurisdictions=("*",), supported_sectors=("*",)),
        control_plane=_control_plane(),
        blob_store=InMemoryBlobStore(),
        vault_repo=InMemoryVaultRepository(),
        search_repo=InMemorySearchRepository(),
        config_create_responses={},
    )
    manager = ConversionJobSearchManager(deps)
    with pytest.raises(Exception, match="_count"):
        manager.handle(
            tenant_id=TENANT,
            jurisdiction="CA-BC",
            sector="onehealth-research",
            request=SimpleNamespace(headers={}, query_params={}),
            body={
                "resourceType": "Parameters",
                "parameter": [
                    {"name": "study", "valueReference": {"reference": STUDY}},
                    {"name": "_count", "valueInteger": count},
                ],
            },
        )
