# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import Any

from .. import __version__
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
from .factory import (
    build_blob_store,
    build_coding_feedback_sink,
    build_control_plane,
    build_search_repository,
    build_subject_link_store,
    build_vault_repository,
)
from .embedded_worker import install_embedded_worker
from .managers import (
    ApiManagerDependencies,
    ConversionBatchManager,
    ConversionPatchManager,
    ConversionSearchManager,
    ConversionUploadManager,
    ConversionUploadPollManager,
    ConnectIcaOrganizationProofVerifierClient,
    OrganizationTenantActivationManager,
    TenantApiKeyManager,
    TenantConfigCreateManager,
    TenantConfigPollManager,
    TokenExchangeManager,
)
from .observability import configure_logging
from .openapi_contract import build_custom_openapi
from .routes_config import register_config_routes
from .routes_digital_twin import register_digital_twin_routes
from .routes_exchange import register_exchange_routes
from .routes_system import register_system_routes
from .routes_tenant_auth import register_tenant_auth_routes
from .routes_organization_tenant import register_organization_tenant_routes
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
    from .auth_pkce import router as pkce_router

    settings = load_settings()
    control_plane = build_control_plane(settings)
    blob_store = build_blob_store(settings)
    vault_repo = build_vault_repository(settings)
    subject_link_store = build_subject_link_store(settings)
    search_repo = build_search_repository(settings)
    config_create_responses: dict[str, dict[str, Any]] = {}

    deps = ApiManagerDependencies(
        settings=settings,
        control_plane=control_plane,
        blob_store=blob_store,
        vault_repo=vault_repo,
        search_repo=search_repo,
        config_create_responses=config_create_responses,
        coding_feedback_sink=build_coding_feedback_sink(settings),
    )
    config_create_manager = TenantConfigCreateManager(deps)
    config_poll_manager = TenantConfigPollManager(deps)
    upload_manager = ConversionUploadManager(deps)
    upload_poll_manager = ConversionUploadPollManager(deps)
    batch_manager = ConversionBatchManager(deps)
    patch_manager = ConversionPatchManager(deps)
    search_manager = ConversionSearchManager(deps)
    tenant_api_key_manager = TenantApiKeyManager(deps)
    exchange_manager = TokenExchangeManager(settings, tenant_api_key_manager=tenant_api_key_manager)
    organization_tenant_activation_manager = (
        OrganizationTenantActivationManager(
            settings=settings,
            control_plane=control_plane,
            verifier=ConnectIcaOrganizationProofVerifierClient(
                base_url=settings.ica_base_url,
                api_key=settings.ica_api_key,
                timeout_seconds=settings.ica_timeout_seconds,
            ),
        )
        if settings.ica_base_url and settings.ica_api_key
        else None
    )

    app = FastAPI(
        title="Preconversion DIDComm API",
        version=__version__,
        docs_url=None,
        description=(
            "Public DIDComm/FAPI contract for adapter configuration and conversion jobs.\n\n"
            "**Functional groups**\n\n"
            "- 1.1 Controller Auth Exchange: `/publisher/cds-{jurisdiction}/v1/{sector}/organization/dataspace/auth/_exchange`\n"
            "- 1.2 Controller API Key Provisioning: `/publisher/cds-{jurisdiction}/v1/{sector}/api-key/org.schema/action/_*`\n"
            "- 2.1 Identity Auth DCR: `/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/identity/auth/_dcr`\n"
            "- 2.2 Identity Auth PKCE Code: `/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/identity/auth/_code`\n"
            "- 2.3 Identity Auth PKCE Token: `/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/identity/auth/_token`\n"
            "- 2.4 Identity Auth Exchange: `/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/identity/auth/_exchange`\n"
            "- 3.1 Tenant Config Request: `_create`\n"
            "- 3.2 Tenant Config Response: `_create-response`\n"
            "- 4.1 Dataset Upload Request: `_upload`\n"
            "- 4.2 Dataset Upload Response: `_upload-response`\n"
            "- 4.3 Dataset Promotion: `_patch`\n"
            "- 4.4 Dataset Search: `_search`\n"
            "- 4.5 Dataset Batch Promotion: `_batch`\n\n"
            "**Identity model**\n\n"
            "Requester identity is taken from DIDComm payload field `iss`. The query parameter `requestedBy` is not used.\n\n"
            "**Authentication**\n\n"
            "- V2 flow: business endpoints use `Authorization: Bearer <access_token>`\n"
            "- `id_token` is used in identity/auth exchange steps, not in business DIDComm payloads\n"
            "- `DEMO_MODE=true`: signature validation is bypassed; temporary legacy payload token fields may still be accepted for compatibility\n"
            "- `DEMO_MODE=false`: Bearer token required and fully validated\n\n"
            "**Operational notes**\n\n"
            "- Terminal job responses expire after `PRECONV_JOB_RESULT_TTL_SECONDS` and then return not found\n"
            "- `/healthz` is deployment-only (readiness/liveness probe) and intentionally excluded from OpenAPI"
        ),
        openapi_tags=[
            {
                "name": "1.1 Controller Auth Exchange",
                "description": "Bootstrap exchange for controller/organization context before tenant-scoped identity auth.",
            },
            {
                "name": "1.2 Controller API Key Provisioning",
                "description": "Create/disable/remove organization API keys. Organization comes from bearer token claims.",
            },
            {
                "name": "2.1 Identity Auth DCR",
                "description": "Tenant-scoped dynamic client registration.",
            },
            {
                "name": "2.2 Identity Auth PKCE Code",
                "description": "Tenant-scoped PKCE code step.",
            },
            {
                "name": "2.3 Identity Auth PKCE Token",
                "description": "Tenant-scoped PKCE token step.",
            },
            {
                "name": "2.4 Identity Auth Exchange",
                "description": "Tenant-scoped auth exchange step.",
            },
            {
                "name": "3.1 Publisher Config Request",
                "description": "Create or update tenant configuration entries through DIDComm plaintext JSON.",
            },
            {
                "name": "3.2 Publisher Config Response",
                "description": "Retrieve terminal tenant configuration result by correlation id (`thid`).",
            },
            {
                "name": "4.1 Publisher Upload Request",
                "description": "Submit conversion jobs with multipart upload or JSON references.",
            },
            {
                "name": "4.2 Publisher Upload Response",
                "description": "Poll asynchronous conversion status using the same thread id (thid).",
            },
            {
                "name": "4.3 Publisher Patch",
                "description": "Promotes internal drafts explicitly flipping the `userSelected` domain.",
            },
            {
                "name": "4.4 Publisher Dataset Search",
                "description": "Standard POST dataset search (FHIR-backed implementation)",
            },
            {
                "name": "4.5 Publisher Batch",
                "description": "Promotes reviewed resources in bulk using the same semantics as `_patch`.",
            },
            {
                "name": "9. Legacy Endpoints",
                "description": "Deprecated aliases from previous route conventions.",
            },
        ],
    )
    app.state.control_plane = control_plane
    app.state.blob_store = blob_store
    app.state.vault_repo = vault_repo
    app.state.subject_link_store = subject_link_store
    app.state.search_repo = search_repo
    app.state.settings = settings

    install_embedded_worker(
        app,
        control_plane=control_plane,
        blob_store=blob_store,
        vault_repo=vault_repo,
        subject_link_store=subject_link_store,
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
    app.include_router(pkce_router)
    register_exchange_routes(app, exchange_manager=exchange_manager)
    register_tenant_auth_routes(app, tenant_api_key_manager=tenant_api_key_manager, settings=settings)
    if organization_tenant_activation_manager is not None:
        register_organization_tenant_routes(app, activation_manager=organization_tenant_activation_manager)

    app.openapi = build_custom_openapi(app)

    return app


app = create_app()
