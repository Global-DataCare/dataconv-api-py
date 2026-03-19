# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from .openapi_constants import PUBLIC_PATH_PARAMS


def rewrite_paths(schema: dict[str, Any]) -> dict[str, Any]:
    paths = schema.get("paths", {})
    if not isinstance(paths, dict):
        return {}

    rewritten_paths: dict[str, Any] = {}
    for raw_path, methods in paths.items():
        public_path = str(raw_path)
        for internal_name, public_name in PUBLIC_PATH_PARAMS.items():
            public_path = public_path.replace(f"{{{internal_name}}}", f"{{{public_name}}}")

        if isinstance(methods, dict):
            for operation in methods.values():
                if not isinstance(operation, dict):
                    continue
                _rewrite_operation_path_params(operation)
        rewritten_paths[public_path] = methods

    schema["paths"] = rewritten_paths
    return rewritten_paths


def set_path_param_description(operation: dict[str, Any], param_name: str, description: str) -> None:
    params = operation.get("parameters")
    if not isinstance(params, list):
        return
    for param in params:
        if isinstance(param, dict) and param.get("in") == "path" and param.get("name") == param_name:
            param["description"] = description


def append_optional_query_thid_parameter(operation: dict[str, Any]) -> None:
    params = operation.setdefault("parameters", [])
    if not isinstance(params, list):
        return
    params.append(
        {
            "name": "thid",
            "in": "query",
            "required": False,
            "schema": {"type": "string", "example": "thid-auto"},
            "description": "Swagger/testing helper. If body.thid is omitted, query thid is accepted.",
        }
    )


def drop_422_validation_response(operation: dict[str, Any]) -> None:
    responses = operation.get("responses")
    if isinstance(responses, dict):
        responses.pop("422", None)


def set_operation_outcome_error_responses(
    operation: dict[str, Any],
    *,
    include_404: bool = False,
) -> None:
    responses = operation.setdefault("responses", {})
    if not isinstance(responses, dict):
        return
    error_content = {
        "application/didcomm-plain+json": {
            "schema": {"$ref": "#/components/schemas/DidcommEarlyErrorResponse"},
        }
    }
    responses["400"] = {"description": "Invalid request.", "content": error_content}
    responses["401"] = {"description": "Authentication failed.", "content": error_content}
    responses["403"] = {"description": "Subject/device disabled or forbidden.", "content": error_content}
    if include_404:
        responses["404"] = {
            "description": "Thread/job not found (or expired).",
            "content": error_content,
        }
    responses["500"] = {"description": "Internal server error.", "content": error_content}
    drop_422_validation_response(operation)


def _rewrite_operation_path_params(operation: dict[str, Any]) -> None:
    params = operation.get("parameters")
    if not isinstance(params, list):
        return
    for param in params:
        if (
            isinstance(param, dict)
            and param.get("in") == "path"
            and isinstance(param.get("name"), str)
            and param["name"] in PUBLIC_PATH_PARAMS
        ):
            param["name"] = PUBLIC_PATH_PARAMS[param["name"]]
    deduped_params: list[dict[str, Any]] = []
    seen_params: set[tuple[str, str]] = set()
    for param in params:
        if not isinstance(param, dict):
            continue
        key = (str(param.get("in", "")), str(param.get("name", "")))
        if key in seen_params:
            continue
        seen_params.add(key)
        deduped_params.append(param)
    operation["parameters"] = deduped_params
