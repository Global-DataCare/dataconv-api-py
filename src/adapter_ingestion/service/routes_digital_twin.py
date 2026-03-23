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
) -> None:
    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/{software_id}/{resource_type}/_upload",
        status_code=202,
        tags=["2.1 V1 Publisher Upload Request"],
        summary="Submit conversion upload",
        description=(
            "Accepts conversion input and enqueues an asynchronous job.\n\n"
            "Accepted transports are `multipart/form-data` with `file`, or "
            "`application/didcomm-plain+json` with top-level DIDComm `attachments[]` carrying the "
            "input file via `data.base64` or `data.links`.\n\n"
            "Use DIDComm metadata fields `iss`, `type`, `thid`, `jti`, `iat`, `exp`. "
            "`thid` is required for correlation and `exp >= iat` is required."
        ),
    )
    @app.post(
        "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software_id}/{resource_type}/_upload",
        status_code=202,
        tags=["2.1 V1 Publisher Upload Request"],
        summary="Submit conversion upload",
        description=(
            "Accepts conversion input and enqueues an asynchronous job.\n\n"
            "Accepted transports are `multipart/form-data` with `file`, or "
            "`application/didcomm-plain+json` with top-level DIDComm `attachments[]` carrying the "
            "input file via `data.base64` or `data.links`.\n\n"
            "Use DIDComm metadata fields `iss`, `type`, `thid`, `jti`, `iat`, `exp`. "
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
        tags=["2.2 V1 Publisher Upload Response"],
        summary="Poll conversion result by thread id",
        response_class=DidcommJSONResponse,
        description=(
            "Returns job status for a previously submitted conversion.\n\n"
            "Use the same DIDComm `thid` sent in `_upload` and include envelope fields "
            "`iss`, `type`, `iat`, `exp`.\n\n"
            "Terminal job responses are retained for `PRECONV_JOB_RESULT_TTL_SECONDS`."
        ),
    )
    @app.post(
        "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software_id}/{resource_type}/_upload-response",
        tags=["2.2 V1 Publisher Upload Response"],
        summary="Poll conversion result by thread id",
        response_class=DidcommJSONResponse,
        description=(
            "Returns job status for a previously submitted conversion.\n\n"
            "Use the same DIDComm `thid` sent in `_upload` and include envelope fields "
            "`iss`, `type`, `iat`, `exp`.\n\n"
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
        tags=["2.3 V1 Publisher Patch"],
        summary="Apply draft promotion via patch",
        response_class=DidcommJSONResponse,
        description=(
            "Promotes a reviewed conversion thread to `userSelected=false` using `thid`.\n\n"
            "Current review flow uses `Composition/_patch` as the governing publication action for a conversion thread. "
            "The implementation keeps the route parameterized, but public examples should use `Composition` here."
        ),
    )
    @app.post(
        "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software_id}/{resource_type}/_patch",
        tags=["2.3 V1 Publisher Patch"],
        summary="Apply draft promotion via patch",
        response_class=DidcommJSONResponse,
        description=(
            "Promotes a reviewed conversion thread to `userSelected=false` using `thid`.\n\n"
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
        tags=["2.5 V1 Publisher Batch"],
        summary="Promote reviewed resources in batch",
        response_class=DidcommJSONResponse,
        description=(
            "Promotes reviewed resources to `userSelected=false` and projects them to search.\n\n"
            "Current publication flow uses `Patient/_batch` as the public example path, even though the runtime keeps "
            "the route parameterized."
        ),
    )
    @app.post(
        "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software_id}/{resource_type}/_batch",
        tags=["2.5 V1 Publisher Batch"],
        summary="Promote reviewed resources in batch",
        response_class=DidcommJSONResponse,
        description=(
            "Promotes reviewed resources to `userSelected=false` and projects them to search.\n\n"
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
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/dataset/{resource_type}/_search",
        tags=["2.4 V1 Publisher Dataset Search"],
        summary="Tenant-scoped FHIR API search",
        response_class=JSONResponse,
        description=(
            "Executes tenant-scoped FHIR-like search over the SQL search projection.\n\n"
            "This is intentionally published under `org.hl7.fhir.api` and not under `digitaltwin`, because the current "
            "phase does not yet expose final `org.hl7.fhir.r4` / `org.hl7.fhir.r5` conversion outputs.\n\n"
            "Supported comparator syntax today is value-prefix based: `ge`, `gt`, `le`, `lt`."
        ),
    )
    @app.post(
        "/host/cds-{jurisdiction}/v1/{sector}/{tenant_id}/org.hl7.fhir.api/{resource_type}/_search",
        tags=["2.4 V1 Publisher Dataset Search"],
        summary="Tenant-scoped FHIR API search",
        response_class=JSONResponse,
        description=(
            "Executes tenant-scoped FHIR-like search over the SQL search projection.\n\n"
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
