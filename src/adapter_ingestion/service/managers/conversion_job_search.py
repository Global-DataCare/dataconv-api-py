# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from gdc_data_utils import FHIR_API_CONTEXT, TaskClaim

from ...runtime import JobStatus
from ..api_support import (
    HTTPException,
    _compose_software_id_token,
    _enforce_auth_context,
    _enforce_supported_scope,
)
from ..research_study import normalize_research_study_reference, sector_requires_professional_research_auth
from .dependencies import ApiManagerDependencies


_TASK_STATUS_BY_JOB_STATUS = {
    JobStatus.QUEUED: "ready",
    JobStatus.RUNNING: "in-progress",
    JobStatus.SUCCEEDED: "completed",
    JobStatus.FAILED: "failed",
}


def project_job_as_task(job: Any) -> dict[str, Any]:
    """Project one internal conversion job as canonical flat Task claims."""
    job_status = str(getattr(job, "status", "") or "").strip().lower()
    task_status = _TASK_STATUS_BY_JOB_STATUS.get(job_status)
    if task_status is None:
        raise ValueError(f"unsupported conversion job status: {job_status}")
    request = getattr(job, "request", None)
    created_at = str(getattr(job, "created_at", "") or "").strip()
    started_at = str(getattr(job, "started_at", "") or "").strip()
    finished_at = str(getattr(job, "finished_at", "") or "").strip()
    claims: dict[str, Any] = {
        "@context": FHIR_API_CONTEXT,
        TaskClaim.IDENTIFIER: str(getattr(job, "job_id", "") or "").strip(),
        TaskClaim.GROUP_IDENTIFIER: str(getattr(job, "thid", "") or "").strip(),
        TaskClaim.STATUS: task_status,
        TaskClaim.BUSINESS_STATUS: job_status,
        TaskClaim.INTENT: "order",
        TaskClaim.CODE: _compose_software_id_token(
            getattr(request, "manufacturer", ""),
            getattr(request, "manufacturer_version", ""),
        ),
        TaskClaim.FOR: str(getattr(request, "research_study_reference", "") or "").strip(),
        TaskClaim.REQUESTER: str(getattr(request, "requested_by", "") or "").strip(),
        TaskClaim.AUTHORED_ON: created_at,
        TaskClaim.LAST_MODIFIED: finished_at or started_at or created_at,
    }
    optional_values = {
        TaskClaim.EXECUTION_PERIOD_START: started_at,
        TaskClaim.EXECUTION_PERIOD_END: finished_at,
        TaskClaim.OUTPUT_VALUE_REFERENCE: str(getattr(job, "result_ref", "") or "").strip(),
        TaskClaim.STATUS_REASON: str(getattr(job, "error", "") or "").strip(),
    }
    claims.update({key: value for key, value in optional_values.items() if value})
    return {
        "resourceType": "Task",
        "id": str(getattr(job, "job_id", "") or "").strip(),
        "meta": {"claims": claims},
    }


def _parameter_values(body: dict[str, Any]) -> dict[str, Any]:
    if str(body.get("resourceType", "") or "").strip() != "Parameters":
        raise HTTPException(status_code=400, detail="job search body must be a FHIR Parameters resource")
    parameters = body.get("parameter")
    if not isinstance(parameters, list):
        raise HTTPException(status_code=400, detail="FHIR Parameters.parameter must be an array")
    values: dict[str, Any] = {}
    for parameter in parameters:
        if not isinstance(parameter, dict):
            continue
        name = str(parameter.get("name", "") or "").strip()
        if not name:
            continue
        value_keys = [key for key in parameter if str(key).startswith("value")]
        if len(value_keys) != 1:
            raise HTTPException(
                status_code=400,
                detail=f"FHIR search parameter '{name}' must contain exactly one value[x]",
            )
        values[name] = parameter[value_keys[0]]
    return values


def _integer_parameter(values: dict[str, Any], name: str, default: int) -> int:
    raw = values.get(name, default)
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{name} must be an integer") from exc


class ConversionJobSearchManager:
    """List every conversion job visible through one study-scoped grant."""

    def __init__(self, deps: ApiManagerDependencies) -> None:
        self._deps = deps

    def handle(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Any,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        _enforce_supported_scope(jurisdiction, sector, self._deps.settings)
        values = _parameter_values(body if isinstance(body, dict) else {})
        raw_study = values.get("study")
        if isinstance(raw_study, dict):
            raw_study = raw_study.get("reference")
        try:
            study = normalize_research_study_reference(raw_study)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        count = _integer_parameter(values, "_count", 20)
        offset = _integer_parameter(values, "_offset", 0)
        if count < 1 or count > 100:
            raise HTTPException(status_code=400, detail="_count must be between 1 and 100")
        if offset < 0:
            raise HTTPException(status_code=400, detail="_offset must be zero or greater")

        auth_header = str(getattr(request, "headers", {}).get("authorization", "") or "")
        _enforce_auth_context(
            {},
            self._deps.settings,
            authorization_header=auth_header,
            require_token=True,
            required_scopes={"dataconv.read"},
            expected_organization=tenant_id,
            expected_research_study=study,
            require_study_research=sector_requires_professional_research_auth(
                sector,
                self._deps.settings,
            ),
        )

        expected_tenant = str(tenant_id or "").strip().lower()
        expected_sector = str(sector or "").strip().lower()
        expected_country = str(jurisdiction or "").strip().upper()
        jobs = [
            job
            for job in self._deps.control_plane.list_jobs(research_study_reference=study)
            if str(job.request.alternate_name or "").strip().lower() == expected_tenant
            and str(job.request.sector or "").strip().lower() == expected_sector
            and str(job.request.country or "").strip().upper() == expected_country
        ]
        jobs.sort(key=lambda job: (str(job.created_at or ""), str(job.job_id or "")), reverse=True)
        page = jobs[offset : offset + count]
        return {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": len(jobs),
            "entry": [
                {
                    "fullUrl": f"urn:uuid:{job.job_id}",
                    "resource": project_job_as_task(job),
                }
                for job in page
            ],
        }
