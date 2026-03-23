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

from .api_support import Body, DidcommJSONResponse, Path, Request, Response


def register_config_routes(app, *, config_create_manager, config_poll_manager) -> None:  # type: ignore[no-untyped-def]
    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/{software_id}/config/_create",
        status_code=202,
        tags=["1.1 V1 Publisher Config Request"],
        summary="Request creation/update of tenant configuration",
        description=(
            "Stores one or more configuration entries for a tenant and software identifier token.\n\n"
            "The requester is resolved from DIDComm field `iss` (did:web employee/system). "
            "Envelope fields `type`, `iat`, and `exp` are required (`exp >= iat`)."
        ),
    )
    @app.post(
        "/host/cds-{jurisdiction}/v1/{sector}/{tenant_id}/{software_id}/config/_create",
        status_code=202,
        tags=["1.1 V1 Publisher Config Request"],
        summary="Request creation/update of tenant configuration",
        description=(
            "Stores one or more configuration entries for a tenant and software identifier token.\n\n"
            "The requester is resolved from DIDComm field `iss` (did:web employee/system). "
            "Envelope fields `type`, `iat`, and `exp` are required (`exp >= iat`)."
        ),
    )
    def create_tenant_config_didcomm(
        sector: str,
        alternate_name: Annotated[
            str,
            Path(description="Stable organization identifier (`taxId` / `VAT`).", alias="tenant_id"),
        ],
        manufacturer: Annotated[str, Path(alias="software_id", description="Software identifier token.")],
        jurisdiction: str,
        request: Request,
        response: Response,
        body: dict[str, Any] = Body(
            default_factory=dict,
            description=(
                "DIDComm plaintext envelope/body. Public profile requires `iss` (did:web employee/system) and `type`."
            ),
        ),
    ) -> Response:
        config_create_manager.handle(
            sector=sector,
            tenant_id=alternate_name,
            jurisdiction=jurisdiction,
            software_id=manufacturer,
            request=request,
            response=response,
            body=body,
        )
        response.status_code = 202
        return response

    @app.post(
        "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant_id}/{software_id}/config/_create-response",
        tags=["1.2 V1 Publisher Config Response"],
        summary="Retrieve response for tenant configuration request",
        response_class=DidcommJSONResponse,
        description=(
            "Retrieves the terminal result (`succeeded` or `failed`) for a previously submitted `_create` action.\n\n"
            "Use the same DIDComm `thid` sent in `_create` and include envelope "
            "fields `iss`, `type`, `iat`, and `exp`.\n\n"
            "POP semantics: once delivered, this response is consumed and cannot be fetched again."
        ),
    )
    @app.post(
        "/host/cds-{jurisdiction}/v1/{sector}/{tenant_id}/{software_id}/config/_create-response",
        tags=["1.2 V1 Publisher Config Response"],
        summary="Retrieve response for tenant configuration request",
        response_class=DidcommJSONResponse,
        description=(
            "Retrieves the terminal result (`succeeded` or `failed`) for a previously submitted `_create` action.\n\n"
            "Use the same DIDComm `thid` sent in `_create` and include envelope "
            "fields `iss`, `type`, `iat`, and `exp`.\n\n"
            "POP semantics: once delivered, this response is consumed and cannot be fetched again."
        ),
    )
    def get_tenant_config_create_response_didcomm(
        sector: str,
        alternate_name: Annotated[
            str,
            Path(description="Stable organization identifier (`taxId` / `VAT`).", alias="tenant_id"),
        ],
        manufacturer: Annotated[str, Path(alias="software_id", description="Software identifier token.")],
        jurisdiction: str,
        request: Request,
        body: dict[str, Any] = Body(default_factory=dict),
    ) -> dict[str, Any]:
        return config_poll_manager.handle(
            sector=sector,
            tenant_id=alternate_name,
            jurisdiction=jurisdiction,
            software_id=manufacturer,
            request=request,
            body=body,
        )
