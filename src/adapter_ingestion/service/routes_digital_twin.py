# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

try:
    from typing import Annotated, Any
except ImportError:  # pragma: no cover
    from typing import Any

    class Annotated:  # type: ignore[no-redef]
        def __class_getitem__(cls, params):
            if isinstance(params, tuple) and params:
                return params[0]
            return params
import json

from .api_support import Body, DIDCOMM_PLAINTEXT_MEDIA_TYPE, DidcommJSONResponse, HTTPException, JSONResponse, Path, Request, Response


def register_digital_twin_routes(  # type: ignore[no-untyped-def]
    app,
    *,
    upload_manager,
    upload_poll_manager,
    patch_manager,
    batch_manager,
    search_manager,
    job_search_manager,
    research_coding_review_manager,
    research_bulk_export_manager,
) -> None:
    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/ResearchSubject/$prepare-review",
        tags=["4.7 Research Coding Review"],
        summary="Prepare durable local text for coding review",
        response_class=JSONResponse,
        description=(
            "Creates missing `ResearchSubject.contained[].meta.codingProposals[]` from durable "
            "local `*-text` claims and the configured terminology service. Proposals never live "
            "on the ResearchSubject or response entry envelope. It does not require or repeat "
            "the original import."
        ),
    )
    def prepare_pending_research_coding_reviews(
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        return research_coding_review_manager.prepare_pending(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            request=request,
            body=body,
        )

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/ResearchSubject/$review-pending",
        tags=["4.7 Research Coding Review"],
        summary="Search durable pending coding reviews by study",
        response_class=JSONResponse,
        description=(
            "Returns ResearchSubject drafts whose contained clinical resources still contain "
            "`meta.codingProposals[]` for the authorized ResearchStudy in pages of at most 1,000 "
            "subjects. Neither the ResearchSubject nor the response entry envelope owns those "
            "proposals. This durable view does not depend on conversion Task retention."
        ),
    )
    def search_pending_research_coding_reviews(
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        return research_coding_review_manager.search_pending(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            request=request,
            body=body,
        )

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/ResearchSubject/$review-candidates",
        tags=["4.7 Research Coding Review"],
        summary="Search governed candidates for one pending proposal",
        response_class=JSONResponse,
        description=(
            "Searches the configured terminology service for one proposal and persists only "
            "server-returned candidates on that authorized ResearchStudy draft."
        ),
    )
    def search_pending_research_coding_candidates(
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        return research_coding_review_manager.search_candidates(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            request=request,
            body=body,
        )

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/ResearchSubject/$review-reclassify",
        tags=["4.7 Research Coding Review"],
        summary="Reclassify one pending local-text proposal",
        response_class=JSONResponse,
        description=(
            "Moves one unresolved proposal to an explicit supported FHIR resource and code field before "
            "terminology search. Existing candidates are cleared because their capability belonged to the old field."
        ),
    )
    def reclassify_pending_research_coding_proposal(
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        return research_coding_review_manager.reclassify_pending(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            request=request,
            body=body,
        )

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/ResearchSubject/$review-discard",
        tags=["4.7 Research Coding Review"],
        summary="Discard one exact pending import draft",
        response_class=JSONResponse,
        description=(
            "Deletes only the still-unreviewed draft graph correlated by ResearchStudy and import thid. "
            "The completed Task remains available as import audit history."
        ),
    )
    def discard_pending_research_import(
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        return research_coding_review_manager.discard_pending_import(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            request=request,
            body=body,
        )

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/ResearchSubject/$review",
        tags=["4.7 Research Coding Review"],
        summary="Apply coding reviews to durable study drafts",
        response_class=JSONResponse,
        description=(
            "Applies explicit human coding selections to the authorized ResearchStudy drafts and "
            "promotes each ResearchSubject only after all of its proposals are resolved."
        ),
    )
    def apply_research_coding_reviews(
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        return research_coding_review_manager.apply_reviews(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            request=request,
            body=body,
        )

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/jobs/Task/_search",
        tags=["4.6 Publisher Job Search"],
        summary="Search study conversion jobs",
        response_class=JSONResponse,
        description=(
            "Lists every conversion job visible through the caller's exact ResearchStudy grant. "
            "The request is a FHIR Parameters resource containing one `study` valueReference and optional "
            "`_count` and `_offset` valueInteger controls. The response is a Bundle with `type=searchset`; "
            "each entry is a Task whose canonical business state lives in `resource.meta.claims`."
        ),
    )
    @app.post(
        "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/jobs/Task/_search",
        tags=["4.6 Publisher Job Search"],
        summary="Search study conversion jobs",
        response_class=JSONResponse,
        include_in_schema=False,
    )
    def search_conversion_jobs(
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        return job_search_manager.handle(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            request=request,
            body=body,
        )

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/{software_id}/{resource_type}/_upload",
        status_code=202,
        tags=["4.1 Publisher Upload Request"],
        summary="Submit conversion upload",
        description=(
            "Accepts conversion input and enqueues an asynchronous job.\n\n"
            "Accepted transports are `multipart/form-data` with `file`, or "
            "`application/didcomm-plain+json` with top-level DIDComm `attachments[]` carrying the "
            "input file via `data.base64` or `data.links`.\n\n"
            "Use DIDComm metadata fields `iss`, `type`, `thid`, `jti`, `iat`, `exp`. "
            "For `sector=onehealth-research` or `sector=animal-research`, `researchStudy.reference` is required and persists the literal FHIR ResearchStudy context. "
            "`thid` is required for correlation and `exp >= iat` is required."
        ),
    )
    @app.post(
        "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software_id}/{resource_type}/_upload",
        status_code=202,
        tags=["4.1 Publisher Upload Request"],
        summary="Submit conversion upload",
        description=(
            "Accepts conversion input and enqueues an asynchronous job.\n\n"
            "Accepted transports are `multipart/form-data` with `file`, or "
            "`application/didcomm-plain+json` with top-level DIDComm `attachments[]` carrying the "
            "input file via `data.base64` or `data.links`.\n\n"
            "Use DIDComm metadata fields `iss`, `type`, `thid`, `jti`, `iat`, `exp`. "
            "For `sector=onehealth-research` or `sector=animal-research`, `researchStudy.reference` is required and persists the literal FHIR ResearchStudy context. "
            "`thid` is required for correlation and `exp >= iat` is required."
        ),
    )
    async def upload_conversion_didcomm(
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        manufacturer: Annotated[
            str,
            Path(
                alias="software_id",
                description=(
                    "Software identifier token. Use `<softwareId>-v<softwareVersion>` when versioned "
                    "(e.g. `qvet-v1.0`)."
                )
            ),
        ],
        resource_type: str,
        request: Request,
        response: Response,
        file: Any = None,
        body: Any = None,
    ) -> None:
        if file is None and body is None:
            raw_content_type = str(request.headers.get("content-type", "") or "").split(";", 1)[0].strip().lower()
            if raw_content_type == "multipart/form-data" or raw_content_type.startswith("multipart/form-data"):
                form = await request.form()
                maybe_file = form.get("file")
                if hasattr(maybe_file, "filename"):
                    file = maybe_file
            elif raw_content_type == DIDCOMM_PLAINTEXT_MEDIA_TYPE or raw_content_type.endswith("+json") or raw_content_type == "application/json":
                raw_body = await request.body()
                if raw_body.strip():
                    try:
                        parsed = json.loads(raw_body.decode("utf-8"))
                    except Exception as exc:
                        raise HTTPException(status_code=400, detail=f"invalid JSON body: {exc}") from exc
                    if not isinstance(parsed, dict):
                        raise HTTPException(status_code=400, detail="request body must be a JSON object")
                    body = parsed
        await upload_manager.handle(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            software_id=manufacturer,
            resource_type=resource_type,
            request=request,
            response=response,
            file=file,
            body=body,
        )
        return None

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/{software_id}/{resource_type}/_upload-response",
        tags=["4.2 Publisher Upload Response"],
        summary="Poll conversion result by thread id",
        response_class=DidcommJSONResponse,
        description=(
            "Returns job status for a previously submitted conversion.\n\n"
            "Use the same DIDComm `thid` sent in `_upload` and include envelope fields "
            "`iss`, `type`, `iat`, `exp`; ResearchStudy-scoped jobs must repeat the same `researchStudy.reference`.\n\n"
            "Terminal job responses are retained for `PRECONV_JOB_RESULT_TTL_SECONDS`."
        ),
    )
    @app.post(
        "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software_id}/{resource_type}/_upload-response",
        tags=["4.2 Publisher Upload Response"],
        summary="Poll conversion result by thread id",
        response_class=DidcommJSONResponse,
        description=(
            "Returns job status for a previously submitted conversion.\n\n"
            "Use the same DIDComm `thid` sent in `_upload` and include envelope fields "
            "`iss`, `type`, `iat`, `exp`; ResearchStudy-scoped jobs must repeat the same `researchStudy.reference`.\n\n"
            "Terminal job responses are retained for `PRECONV_JOB_RESULT_TTL_SECONDS`."
        ),
    )
    def get_conversion_upload_response_didcomm(
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        manufacturer: Annotated[
            str,
            Path(
                alias="software_id",
                description=(
                    "Software identifier token. Use `<softwareId>-v<softwareVersion>` when versioned "
                    "(e.g. `qvet-v1.0`)."
                )
            ),
        ],
        resource_type: str,
        response: Response,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        return upload_poll_manager.handle(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            software_id=manufacturer,
            resource_type=resource_type,
            response=response,
            request=request,
            body=body,
        )

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/{software_id}/{resource_type}/_patch",
        tags=["4.3 Publisher Patch"],
        summary="Apply draft promotion via patch",
        response_class=DidcommJSONResponse,
        description=(
            "Saves coding decisions and publishes each fully reviewed ResearchSubject using `thid`.\n\n"
            "For ResearchStudy-scoped jobs, the request must repeat the exact `researchStudy.reference` stored by upload. "
            "Current review flow uses `Composition/_patch` as the governing publication action for a conversion thread. "
            "The implementation keeps the route parameterized, but public examples should use `Composition` here."
        ),
    )
    @app.post(
        "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software_id}/{resource_type}/_patch",
        tags=["4.3 Publisher Patch"],
        summary="Apply draft promotion via patch",
        response_class=DidcommJSONResponse,
        description=(
            "Saves coding decisions and publishes each fully reviewed ResearchSubject using `thid`.\n\n"
            "For ResearchStudy-scoped jobs, the request must repeat the exact `researchStudy.reference` stored by upload. "
            "Current review flow uses `Composition/_patch` as the governing publication action for a conversion thread. "
            "The implementation keeps the route parameterized, but public examples should use `Composition` here."
        ),
    )
    def patch_conversion_didcomm(
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        manufacturer: Annotated[str, Path(alias="software_id", description="Software identifier token.")],
        resource_type: Annotated[
            str,
            Path(
                description="FHIR resource type governed by the patch action. Public review examples use `Composition`.",
                example="Composition",
            ),
        ],
        response: Response,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        return patch_manager.handle(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            software_id=manufacturer,
            resource_type=resource_type,
            response=response,
            request=request,
            body=body,
        )

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/{software_id}/{resource_type}/_batch",
        tags=["4.5 Publisher Batch"],
        summary="Promote reviewed resources in batch",
        response_class=DidcommJSONResponse,
        description=(
            "Publishes resources only after their ResearchSubject has no mandatory proposals pending.\n\n"
            "Current publication flow uses `Patient/_batch` as the public example path, even though the runtime keeps "
            "the route parameterized."
        ),
    )
    @app.post(
        "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software_id}/{resource_type}/_batch",
        tags=["4.5 Publisher Batch"],
        summary="Promote reviewed resources in batch",
        response_class=DidcommJSONResponse,
        description=(
            "Publishes resources only after their ResearchSubject has no mandatory proposals pending.\n\n"
            "Current publication flow uses `Patient/_batch` as the public example path, even though the runtime keeps "
            "the route parameterized."
        ),
    )
    def batch_conversion_didcomm(
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        manufacturer: Annotated[str, Path(alias="software_id", description="Software identifier token.")],
        resource_type: Annotated[
            str,
            Path(
                description="FHIR resource type governed by the batch action. Public publication examples use `Patient`.",
                example="Patient",
            ),
        ],
        response: Response,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        return batch_manager.handle(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            software_id=manufacturer,
            resource_type=resource_type,
            response=response,
            request=request,
            body=body,
        )

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/ResearchSubject/$summary",
        tags=["4.4 Publisher Dataset Search"],
        summary="Materialize one authorized research subject document",
        response_class=JSONResponse,
        description=(
            "Materializes one ResearchSubject selected from a study-scoped search as a FHIR document Bundle. "
            "The Bundle is suitable for the same read-only health-data viewer used for an individual summary."
        ),
    )
    def materialize_research_subject_summary(
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        return search_manager.handle_summary(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            request=request,
            body=body,
        )

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/ResearchSubject/$tag",
        tags=["4.4 Publisher Dataset Search"],
        summary="Save a researcher-owned ResearchSubject workset marker",
        response_class=JSONResponse,
        description=(
            "Stores an independent researcher-owned working-selection Composition with a ledger-safe tag. "
            "It never mutates or copies the canonical ResearchSubject twin."
        ),
    )
    def tag_research_subject(
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        return search_manager.handle_tag(
            tenant_id=tenant_id, jurisdiction=jurisdiction, sector=sector, request=request, body=body,
        )

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/Group",
        tags=["4.4 Publisher Dataset Search"],
        summary="Create one study-scoped export Group",
        response_class=JSONResponse,
        description=(
            "Creates an actual FHIR Group whose members are pseudonymous Patient references belonging to one "
            "authorized ResearchStudy. The stored business representation remains claims-first."
        ),
    )
    def create_research_export_group(
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        response: Response,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        group = research_bulk_export_manager.create_group(
            tenant_id=tenant_id, jurisdiction=jurisdiction, sector=sector, request=request, body=body,
        )
        response.status_code = 201
        response.headers["Location"] = (
            f"/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/Group/{group['id']}"
        )
        return group

    def _bulk_parameters(body: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
        output_format = "application/fhir+ndjson"
        resource_types: list[str] = []
        for parameter in body.get("parameter", []) if body.get("resourceType") == "Parameters" else []:
            if not isinstance(parameter, dict):
                continue
            if parameter.get("name") == "_outputFormat":
                output_format = str(parameter.get("valueString", "") or "")
            elif parameter.get("name") == "_type":
                value = str(parameter.get("valueString", "") or "")
                resource_types.extend(item.strip() for item in value.split(",") if item.strip())
        return output_format, tuple(resource_types)

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/Group/{group_id}/$export",
        tags=["4.4 Publisher Dataset Search"],
        summary="Start a FHIR Bulk Data Group export",
        response_class=JSONResponse,
    )
    def kickoff_research_group_export(
        tenant_id: str, jurisdiction: str, sector: str, group_id: str,
        request: Request, body: dict[str, Any] = Body(default_factory=dict),
    ):
        if "respond-async" not in str(request.headers.get("prefer", "") or "").lower():
            raise HTTPException(status_code=400, detail="Prefer: respond-async is required")
        output_format, resource_types = _bulk_parameters(body)
        result = research_bulk_export_manager.kickoff(
            tenant_id=tenant_id, jurisdiction=jurisdiction, sector=sector, group_id=group_id,
            request=request, output_format=output_format, resource_types=resource_types,
        )
        return Response(status_code=202, headers={"Content-Location": result["contentLocation"]})

    @app.get(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/Group/{group_id}/$export",
        tags=["4.4 Publisher Dataset Search"],
        summary="Start a FHIR Bulk Data Group export",
        response_class=JSONResponse,
    )
    def kickoff_research_group_export_get(
        tenant_id: str, jurisdiction: str, sector: str, group_id: str, request: Request,
    ):
        if "respond-async" not in str(request.headers.get("prefer", "") or "").lower():
            raise HTTPException(status_code=400, detail="Prefer: respond-async is required")
        output_format = str(request.query_params.get("_outputFormat", "application/fhir+ndjson") or "")
        resource_types = tuple(
            item.strip() for item in str(request.query_params.get("_type", "") or "").split(",") if item.strip()
        )
        result = research_bulk_export_manager.kickoff(
            tenant_id=tenant_id, jurisdiction=jurisdiction, sector=sector, group_id=group_id,
            request=request, output_format=output_format, resource_types=resource_types,
        )
        return Response(status_code=202, headers={"Content-Location": result["contentLocation"]})

    @app.get(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/bulk-status/{job_id}",
        tags=["4.4 Publisher Dataset Search"], summary="Poll a FHIR Bulk Data export",
    )
    def poll_research_group_export(
        tenant_id: str, jurisdiction: str, sector: str, job_id: str, request: Request,
    ):
        result = research_bulk_export_manager.status(
            tenant_id=tenant_id, jurisdiction=jurisdiction, sector=sector, job_id=job_id, request=request,
        )
        if result["body"] is None:
            return Response(status_code=result["status"], headers=result["headers"])
        return JSONResponse(status_code=result["status"], headers=result["headers"], content=result["body"])

    @app.delete(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/bulk-status/{job_id}",
        tags=["4.4 Publisher Dataset Search"], summary="Cancel a FHIR Bulk Data export",
    )
    def cancel_research_group_export(
        tenant_id: str, jurisdiction: str, sector: str, job_id: str, request: Request,
    ):
        research_bulk_export_manager.cancel(
            tenant_id=tenant_id, jurisdiction=jurisdiction, sector=sector, job_id=job_id, request=request,
        )
        return Response(status_code=202)

    @app.get(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/bulk-files/{job_id}/{resource_type}.ndjson",
        tags=["4.4 Publisher Dataset Search"], summary="Download one FHIR Bulk Data NDJSON file",
    )
    def download_research_group_export_file(
        tenant_id: str, jurisdiction: str, sector: str, job_id: str, resource_type: str, request: Request,
    ):
        payload = research_bulk_export_manager.download(
            tenant_id=tenant_id, jurisdiction=jurisdiction, sector=sector, job_id=job_id,
            resource_type=resource_type, request=request,
        )
        return Response(content=payload, media_type="application/fhir+ndjson")

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/{resource_type}/_search",
        tags=["4.4 Publisher Dataset Search"],
        summary="Tenant-scoped FHIR API search",
        response_class=JSONResponse,
        description=(
            "Executes tenant-scoped FHIR search over the SQL search projection. The request body accepts a FHIR "
            "`Parameters` resource and the response is a `Bundle` with `type=searchset`.\n\n"
            "ResearchSubject search requires the standard `study` reference parameter. It also accepts qualified "
            "`ResourceType.search-parameter` entries and returns the intersection of matching subject identifiers "
            "across resource families. "
            "This is intentionally published under `org.hl7.fhir.api` and not under `digitaltwin`, because the current "
            "phase does not yet expose final `org.hl7.fhir.r4` / `org.hl7.fhir.r5` conversion outputs.\n\n"
            "Supported comparator syntax today is value-prefix based: `ge`, `gt`, `le`, `lt`."
        ),
    )
    @app.post(
        "/host/cds-{jurisdiction}/v1/{sector}/{tenant_id}/org.hl7.fhir.api/{resource_type}/_search",
        tags=["4.4 Publisher Dataset Search"],
        summary="Tenant-scoped FHIR API search",
        response_class=JSONResponse,
        description=(
            "Executes tenant-scoped FHIR search over the SQL search projection. The request body accepts a FHIR "
            "`Parameters` resource and the response is a `Bundle` with `type=searchset`.\n\n"
            "ResearchSubject search requires the standard `study` reference parameter. It also accepts qualified "
            "`ResourceType.search-parameter` entries and returns the intersection of matching subject identifiers "
            "across resource families. "
            "This is intentionally published under `org.hl7.fhir.api` and not under `digitaltwin`, because the current "
            "phase does not yet expose final `org.hl7.fhir.r4` / `org.hl7.fhir.r5` conversion outputs.\n\n"
            "Supported comparator syntax today is value-prefix based: `ge`, `gt`, `le`, `lt`."
        ),
    )
    def search_resources_native(
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        resource_type: Annotated[
            str,
            Path(
                description="FHIR resource type to search in the tenant-scoped API view.",
                example="DocumentReference",
            ),
        ],
        response: Response,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        return search_manager.handle(
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            resource_type=resource_type,
            response=response,
            request=request,
            body=body,
        )
