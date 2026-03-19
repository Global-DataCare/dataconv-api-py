# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from .openapi_cleanup import prune_unused_schemas
from .openapi_components import install_components
from .openapi_examples import load_example_json
from .openapi_operations import configure_operations, configure_schema_metadata
from .openapi_paths import rewrite_paths


def build_custom_openapi(app):
    from fastapi.openapi.utils import get_openapi

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=app.openapi_tags,
        )
        rewritten_paths = rewrite_paths(schema)
        configure_schema_metadata(schema)
        install_components(schema)
        configure_operations(
            rewritten_paths,
            create_request_example=load_example_json("examples/openapi/config-create-request.didcomm.json"),
            create_response_request_example=load_example_json(
                "examples/openapi/config-create-response-request.didcomm.json"
            ),
            upload_request_example=load_example_json("examples/openapi/upload-request-link.didcomm.json"),
            upload_response_request_example=load_example_json("examples/openapi/upload-response-request.didcomm.json"),
        )
        prune_unused_schemas(schema)

        app.openapi_schema = schema
        return app.openapi_schema

    return custom_openapi
