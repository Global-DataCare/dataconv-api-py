# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from .openapi_constants import BATCH_PATH, CREATE_PATH, CREATE_RESPONSE_PATH, PATCH_PATH, SEARCH_PATH, UPLOAD_PATH, UPLOAD_RESPONSE_PATH
from .openapi_paths import (
    append_optional_query_thid_parameter,
    drop_422_validation_response,
    set_operation_outcome_error_responses,
    set_path_param_description,
)


def configure_schema_metadata(schema: dict[str, Any]) -> None:
    info = schema.get("info")
    if isinstance(info, dict):
        info["title"] = "Preconversion DIDComm API"
        info["version"] = "0.3.0"
        info["description"] = (
            "Public DIDComm/FAPI contract for tenant configuration and conversion jobs.\n\n"
            "Sections in this OpenAPI:\n"
            "1.1) Tenant Configuration Request (_create)\n"
            "1.2) Tenant Configuration Response (_create-response)\n"
            "2.1) Conversion Upload Request (_upload)\n"
            "2.2) Conversion Upload Response (_upload-response)\n"
            "2.3) Conversion Patch (_patch)\n"
            "2.4) Tenant-scoped FHIR API Search (_search)\n"
            "2.5) Conversion Batch (_batch)\n\n"
            "Requester identity is extracted from DIDComm `iss`.\n"
            "Token enforcement profile is configured with `PRECONV_AUTH_MODE` (`parse-only` is demo/internal-only).\n"
            "Terminal job responses expire after `PRECONV_JOB_RESULT_TTL_SECONDS`.\n"
            "Deployment probe endpoint `/healthz` is intentionally excluded from this contract."
        )

    schema["tags"] = [
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
            "description": "Promote a reviewed conversion thread. Public examples use `Composition/_patch`.",
        },
        {
            "name": "2.4 FHIR-like Search API",
            "description": "Tenant-scoped host search under `org.hl7.fhir.api`, backed by the SQL projection.",
        },
        {
            "name": "2.5 Conversion Batch",
            "description": "Promote reviewed resources in bulk. Public examples use `Patient/_batch`.",
        },
    ]


def configure_operations(
    rewritten_paths: dict[str, Any],
    *,
    create_request_example: dict[str, Any],
    create_response_request_example: dict[str, Any],
    upload_request_example: dict[str, Any],
    upload_response_request_example: dict[str, Any],
) -> None:
    create_operation = rewritten_paths.get(CREATE_PATH, {}).get("post")
    create_response_operation = rewritten_paths.get(CREATE_RESPONSE_PATH, {}).get("post")
    upload_operation = rewritten_paths.get(UPLOAD_PATH, {}).get("post")
    upload_response_operation = rewritten_paths.get(UPLOAD_RESPONSE_PATH, {}).get("post")
    patch_operation = rewritten_paths.get(PATCH_PATH, {}).get("post")
    batch_operation = rewritten_paths.get(BATCH_PATH, {}).get("post")
    search_operation = rewritten_paths.get(SEARCH_PATH, {}).get("post")

    if isinstance(create_operation, dict):
        create_operation["security"] = [{"BearerAuth": []}]
        set_path_param_description(
            create_operation,
            "tenant-id",
            "Stable organization identifier (`taxId` / `VAT`) used as tenant id.",
        )
        set_path_param_description(
            create_operation,
            "jurisdiction",
            "CDS country code segment used in the public route, e.g. `ES`.",
        )
        create_operation["requestBody"] = {
            "required": True,
            "content": {
                "application/didcomm-plain+json": {
                    "schema": {"$ref": "#/components/schemas/DidcommNewOrgConfigCreateRequest"},
                    "example": create_request_example,
                    "examples": {
                        "didcommCreateRequest": {
                            "summary": "Create/update tenant config",
                            "value": create_request_example,
                        }
                    },
                }
            },
        }
        create_responses = create_operation.setdefault("responses", {})
        if isinstance(create_responses, dict):
            create_responses["202"] = {
                "description": "Configuration request accepted. Response body is empty; poll using Location.",
                "headers": {
                    "Location": {
                        "description": "Response endpoint URL (`.../_create-response?thid=...`).",
                        "schema": {"type": "string"},
                    },
                    "Retry-After": {
                        "description": "Recommended delay before checking `_create-response`.",
                        "schema": {"type": "string", "example": "1"},
                    },
                },
            }
        set_operation_outcome_error_responses(create_operation)

    if isinstance(create_response_operation, dict):
        create_response_operation["security"] = [{"BearerAuth": []}]
        set_path_param_description(
            create_response_operation,
            "tenant-id",
            "Stable organization identifier (`taxId` / `VAT`) used as tenant id.",
        )
        create_response_operation["requestBody"] = {
            "required": True,
            "content": {
                "application/didcomm-plain+json": {
                    "schema": {"$ref": "#/components/schemas/DidcommNewOrgConfigPollRequest"},
                    "example": create_response_request_example,
                    "examples": {
                        "didcommCreateResponseRequest": {
                            "summary": "Poll config response",
                            "value": create_response_request_example,
                        }
                    },
                }
            },
        }
        append_optional_query_thid_parameter(create_response_operation)
        create_response_responses = create_response_operation.setdefault("responses", {})
        if isinstance(create_response_responses, dict):
            create_response_responses["200"] = {
                "description": "Configuration request finished. Returns a DIDComm-like `Bundle` (`batch-response`) with per-entry `response.outcome` (single-delivery POP semantics).",
                "content": {
                    "application/didcomm-plain+json": {
                        "schema": {"$ref": "#/components/schemas/DidcommNewOrgConfigPollResponse"}
                    }
                },
            }
        set_operation_outcome_error_responses(create_response_operation, include_404=True)

    if isinstance(upload_operation, dict):
        upload_operation["security"] = [{"BearerAuth": []}]
        set_path_param_description(
            upload_operation,
            "tenant-id",
            "Stable organization identifier (`taxId` / `VAT`). It appears in both route segments and must match.",
        )
        upload_operation["requestBody"] = {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {"$ref": "#/components/schemas/DidcommUploadMultipartRequest"}
                },
                "application/didcomm-plain+json": {
                    "schema": {"$ref": "#/components/schemas/DidcommUploadDidcommPlaintextRequest"},
                    "example": upload_request_example,
                    "examples": {
                        "didcommUploadWithLink": {
                            "summary": "Upload via DIDComm attachment link",
                            "value": upload_request_example,
                        }
                    },
                },
            },
        }
        upload_responses = upload_operation.setdefault("responses", {})
        if isinstance(upload_responses, dict):
            upload_responses["202"] = {
                "description": "Upload accepted and queued. Poll later using Location and the same thid.",
                "headers": {
                    "Location": {
                        "description": "Polling endpoint URL (`.../_upload-response?thid=...`).",
                        "schema": {"type": "string"},
                    },
                    "Retry-After": {
                        "description": "Recommended polling delay in seconds.",
                        "schema": {"type": "string", "example": "5"},
                    },
                },
            }
        set_operation_outcome_error_responses(upload_operation)

    if isinstance(upload_response_operation, dict):
        upload_response_operation["security"] = [{"BearerAuth": []}]
        set_path_param_description(
            upload_response_operation,
            "tenant-id",
            "Stable organization identifier (`taxId` / `VAT`). It appears in both route segments and must match.",
        )
        upload_response_operation["requestBody"] = {
            "required": True,
            "content": {
                "application/didcomm-plain+json": {
                    "schema": {"$ref": "#/components/schemas/DidcommUploadResponseRequest"},
                    "example": upload_response_request_example,
                    "examples": {
                        "didcommUploadResponseRequest": {
                            "summary": "Poll upload response",
                            "value": upload_response_request_example,
                        }
                    },
                }
            },
        }
        append_optional_query_thid_parameter(upload_response_operation)
        upload_response_responses = upload_response_operation.setdefault("responses", {})
        if isinstance(upload_response_responses, dict):
            upload_response_responses["200"] = {
                "description": "Job finished. Returns a DIDComm `Bundle` (`batch-response`) with `body.issues` plus one `body.data[]` item per processed upload input (current profile: exactly one attachment/input).",
                "content": {
                    "application/didcomm-plain+json": {
                        "schema": {"$ref": "#/components/schemas/DidcommPollResponse"}
                    }
                },
            }
            upload_response_responses["202"] = {
                "description": "Job still in progress (queued or running). Response still uses DIDComm `Bundle` (`batch-response`) with `body.data[0].response.status = 202`.",
                "headers": {
                    "Retry-After": {
                        "description": "Recommended polling delay in seconds.",
                        "schema": {"type": "string", "example": "5"},
                    },
                },
                "content": {
                    "application/didcomm-plain+json": {
                        "schema": {"$ref": "#/components/schemas/DidcommPollResponse"}
                    }
                },
            }
        set_operation_outcome_error_responses(upload_response_operation, include_404=True)

    if isinstance(patch_operation, dict):
        patch_operation["security"] = [{"BearerAuth": []}]
        patch_operation["requestBody"] = {
            "required": True,
            "content": {
                "application/didcomm-plain+json": {
                    "schema": {"$ref": "#/components/schemas/DidcommPromotionRequest"},
                    "example": {
                        "iss": "did:web:clinic.example:employee:it:loader",
                        "id_token": "demo-token",
                        "thid": "up-qvet-20260315-001",
                        "type": "https://didcomm.org/plaintext/2.0/message",
                        "iat": 1760000000,
                        "exp": 1760003600,
                    },
                }
            },
        }
        patch_operation.setdefault("responses", {})["200"] = {
            "description": "Promotion executed for the reviewed conversion thread.",
            "content": {
                "application/didcomm-plain+json": {
                    "schema": {"$ref": "#/components/schemas/DidcommPromotionResponse"}
                }
            },
        }
        set_operation_outcome_error_responses(patch_operation, include_404=True)

    if isinstance(batch_operation, dict):
        batch_operation["security"] = [{"BearerAuth": []}]
        batch_operation["requestBody"] = {
            "required": True,
            "content": {
                "application/didcomm-plain+json": {
                    "schema": {"$ref": "#/components/schemas/DidcommPromotionRequest"},
                    "example": {
                        "iss": "did:web:clinic.example:employee:it:loader",
                        "id_token": "demo-token",
                        "thid": "up-qvet-20260315-001",
                        "type": "https://didcomm.org/plaintext/2.0/message",
                        "iat": 1760000000,
                        "exp": 1760003600,
                    },
                }
            },
        }
        batch_operation.setdefault("responses", {})["200"] = {
            "description": "Bulk promotion executed for the reviewed publication unit.",
            "content": {
                "application/didcomm-plain+json": {
                    "schema": {"$ref": "#/components/schemas/DidcommPromotionResponse"}
                }
            },
        }
        set_operation_outcome_error_responses(batch_operation, include_404=True)

    if isinstance(search_operation, dict):
        search_operation["security"] = [{"BearerAuth": []}]
        set_path_param_description(
            search_operation,
            "tenant-id",
            "Stable organization identifier (`taxId` / `VAT`) scoped to the tenant-local FHIR API view.",
        )
        search_operation["requestBody"] = {
            "required": False,
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/TenantScopedFhirSearchRequest"},
                    "examples": {
                        "documentReferenceDateFrom2026": {
                            "summary": "DocumentReference from 2026 onwards",
                            "value": {
                                "userselected": "false",
                                "date": "ge2026-01-01",
                            },
                        }
                    },
                }
            },
        }
        search_operation.setdefault("responses", {})["200"] = {
            "description": "Tenant-scoped search results from the SQL projection.",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/TenantScopedFhirSearchResponse"}
                }
            },
        }
        set_operation_outcome_error_responses(search_operation, include_404=False)

    for operation in (
        create_operation,
        create_response_operation,
        upload_operation,
        upload_response_operation,
        patch_operation,
        batch_operation,
        search_operation,
    ):
        if isinstance(operation, dict):
            drop_422_validation_response(operation)
