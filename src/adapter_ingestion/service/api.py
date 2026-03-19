# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import Any

from ..runtime import ConfigKey
from .api_support import (
    DIDCOMM_PLAINTEXT_MEDIA_TYPE,
    FastAPI,
    HTTPException,
    JSONResponse,
    Request,
    RequestValidationError,
    _bundle_api_error_envelope,
    _diagnostics_from_error_detail,
    _error_issue_code,
)
from .factory import build_blob_store, build_control_plane, build_search_repository, build_vault_repository
from .embedded_worker import install_embedded_worker
from .managers import (
    ApiManagerDependencies,
    ConversionBatchManager,
    ConversionPatchManager,
    ConversionUploadManager,
    ConversionUploadPollManager,
    TenantConfigCreateManager,
    TenantConfigPollManager,
    ConversionSearchManager,
)
from .observability import configure_logging
from .openapi_contract import build_custom_openapi
from .routes_config import register_config_routes
from .routes_digital_twin import register_digital_twin_routes
from .routes_system import register_system_routes
from .settings import load_settings

_LOGGER = logging.getLogger(__name__)


def create_app():
    configure_logging()
    # TODO(rename-repo): this service will move from `adapter-ingestion-py` to `dataconv-api-py`.
    if FastAPI is None:
        raise RuntimeError(
            "Missing dependencies for HTTP service. Install with: "
            "pip install 'adapter-ingestion-py[api]'"
        )

    settings = load_settings()
    control_plane = build_control_plane(settings)
    blob_store = build_blob_store(settings)
    vault_repo = build_vault_repository(settings)
    search_repo = build_search_repository(settings)
    config_create_responses: dict[str, dict[str, Any]] = {}

    deps = ApiManagerDependencies(
        settings=settings,
        control_plane=control_plane,
        blob_store=blob_store,
        vault_repo=vault_repo,
        search_repo=search_repo,
        config_create_responses=config_create_responses,
    )
    config_create_manager = TenantConfigCreateManager(deps)
    config_poll_manager = TenantConfigPollManager(deps)
    upload_manager = ConversionUploadManager(deps)
    upload_poll_manager = ConversionUploadPollManager(deps)
    batch_manager = ConversionBatchManager(deps)
    patch_manager = ConversionPatchManager(deps)
    search_manager = ConversionSearchManager(deps)

    app = FastAPI(
        title="Preconversion DIDComm API",
        version="0.2.1",
        docs_url=None,
        description=(
            "Public DIDComm/FAPI contract for adapter configuration and conversion jobs.\n\n"
            "Business endpoints are POST-only and grouped as request/response pairs:\n"
            "1.1) tenant configuration request (_create), 1.2) tenant configuration response (_create-response),\n"
            "2.1) conversion upload request (_upload), 2.2) conversion upload response (_upload-response).\n\n"
            "Requester identity is taken from DIDComm payload field `iss` (query parameter `requestedBy` is not used).\n\n"
            "Token enforcement profile is controlled by `PRECONV_AUTH_MODE` (`parse-only`, `verify-id-token`, "
            "`verify-vp-token`, `verify-both`). `parse-only` is demo/internal-only and should not be used in "
            "production.\n"
            "Terminal job responses expire after `PRECONV_JOB_RESULT_TTL_SECONDS` and then return not found.\n\n"
            "`/healthz` is deployment-only (readiness/liveness probe) and intentionally excluded from OpenAPI."
        ),
        openapi_tags=[
            {
                "name": "1.1 Tenant Configuration Request",
                "description": "Create or update tenant configuration entries through DIDComm plaintext JSON.",
            },
            {
                "name": "1.2 Tenant Configuration Response",
                "description": "Retrieve terminal tenant configuration result by correlation id (`thid`).",
            },
            {
                "name": "2.1 Conversion Upload Request",
                "description": "Submit conversion jobs with multipart upload or JSON references.",
            },
            {
                "name": "2.2 Conversion Upload Response",
                "description": "Poll asynchronous conversion status using the same thread id (thid).",
            },
            {
                "name": "2.3 Conversion Patch",
                "description": "Promotes internal drafts explicitly flipping the `userSelected` domain.",
            },
            {
                "name": "2.4 FHIR-like Search API",
                "description": "Standard POST FHIR-like search via query params and body",
            },
            {
                "name": "2.5 Conversion Batch",
                "description": "Promotes reviewed resources in bulk using the same semantics as `_patch`.",
            },
        ],
    )
    app.state.control_plane = control_plane
    app.state.blob_store = blob_store
    app.state.vault_repo = vault_repo
    app.state.search_repo = search_repo
    app.state.settings = settings

    install_embedded_worker(
        app,
        control_plane=control_plane,
        blob_store=blob_store,
        vault_repo=vault_repo,
        settings=settings,
    )

    if RequestValidationError is not None and JSONResponse is not None:

        @app.exception_handler(RequestValidationError)
        async def _request_validation_to_operation_outcome(  # type: ignore[no-untyped-def]
            request: Request, exc: RequestValidationError
        ):
            diagnostics = _diagnostics_from_error_detail(exc.errors())
            return JSONResponse(
                status_code=400,
                media_type=DIDCOMM_PLAINTEXT_MEDIA_TYPE,
                content=_bundle_api_error_envelope(
                    service_iss=settings.default_audience_did,
                    aud="",
                    thid="",
                    severity="error",
                    code="invalid",
                    diagnostics=diagnostics,
                ),
            )

    if JSONResponse is not None:

        @app.exception_handler(HTTPException)
        async def _http_exception_to_operation_outcome(  # type: ignore[no-untyped-def]
            request: Request, exc: HTTPException
        ):
            status_code = int(getattr(exc, "status_code", 400) or 400)
            diagnostics = _diagnostics_from_error_detail(getattr(exc, "detail", "request failed"))
            return JSONResponse(
                status_code=status_code,
                media_type=DIDCOMM_PLAINTEXT_MEDIA_TYPE,
                content=_bundle_api_error_envelope(
                    service_iss=settings.default_audience_did,
                    aud="",
                    thid="",
                    severity="error" if status_code >= 400 else "information",
                    code=_error_issue_code(status_code),
                    diagnostics=diagnostics,
                ),
            )

        @app.exception_handler(Exception)
        async def _unexpected_exception_to_operation_outcome(  # type: ignore[no-untyped-def]
            request: Request, exc: Exception
        ):
            _LOGGER.exception("Unhandled API error", extra={"path": str(request.url.path)})
            return JSONResponse(
                status_code=500,
                media_type=DIDCOMM_PLAINTEXT_MEDIA_TYPE,
                content=_bundle_api_error_envelope(
                    service_iss=settings.default_audience_did,
                    aud="",
                    thid="",
                    severity="error",
                    code=_error_issue_code(500),
                    diagnostics="internal server error",
                ),
            )

    register_system_routes(app, settings)
    register_config_routes(
        app,
        config_create_manager=config_create_manager,
        config_poll_manager=config_poll_manager,
    )
    register_digital_twin_routes(
        app,
        upload_manager=upload_manager,
        upload_poll_manager=upload_poll_manager,
        patch_manager=patch_manager,
        batch_manager=batch_manager,
        search_manager=search_manager,
    )

    app.openapi = build_custom_openapi(app)

    return app


app = create_app()
