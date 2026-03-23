# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from .openapi_constants import API_KEY_CREATE_PATH, API_KEY_DISABLE_PATH, API_KEY_REMOVE_PATH, BATCH_PATH, CREATE_PATH, CREATE_RESPONSE_PATH, EXCHANGE_PATH, OAUTH_TOKEN_PATH, PATCH_PATH, SEARCH_PATH, UPLOAD_PATH, UPLOAD_RESPONSE_PATH
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
        info["version"] = "0.6.0"
        info["description"] = (
            "Public DIDComm/FAPI contract for tenant configuration and conversion jobs.\n\n"
            "**Functional groups**\n\n"
            "- 1.1 Publisher Config Request: `_create`\n"
            "- 1.2 Publisher Config Response: `_create-response`\n"
            "- 2.1 Publisher Upload Request: `_upload`\n"
            "- 2.2 Publisher Upload Response: `_upload-response`\n"
            "- 2.3 Publisher Patch: `_patch`\n"
            "- 2.4 Publisher Dataset Search: `_search`\n"
            "- 2.5 Publisher Batch: `_batch`\n"
            "- 1.3 Tenant Auth API Keys: `_create`, `_disable`, `_remove`\n"
            "- 9.x Legacy aliases: deprecated compatibility routes\n\n"
            "**Identity model**\n\n"
            "Requester identity is extracted from DIDComm `iss`.\n\n"
            "**Authentication**\n\n"
            "- `DEMO_MODE=true`: no auth required\n"
            "- `DEMO_MODE=false`: Bearer token from `/exchange` required\n\n"
            "**Operational notes**\n\n"
            "- Terminal job responses expire after `PRECONV_JOB_RESULT_TTL_SECONDS`\n"
            "- Deployment probe endpoint `/healthz` is intentionally excluded from this contract"
        )

    schema["tags"] = [
        {
            "name": "1.1 Publisher Config Request",
            "description": "Create or update tenant configuration entries through DIDComm plaintext JSON.",
        },
        {
            "name": "1.2 Publisher Config Response",
            "description": "Retrieve terminal tenant configuration result by correlation id (`thid`).",
        },
        {
            "name": "2.1 Publisher Upload Request",
            "description": "Submit conversion jobs with multipart upload or JSON references.",
        },
        {
            "name": "2.2 Publisher Upload Response",
            "description": "Poll asynchronous conversion status using the same thread id (thid).",
        },
        {
            "name": "2.3 Publisher Patch",
            "description": "Promote a reviewed conversion thread. Public examples use `Composition/_patch`.",
        },
        {
            "name": "2.4 Publisher Dataset Search",
            "description": "Tenant-scoped dataset search endpoint (FHIR-backed implementation).",
        },
        {
            "name": "2.5 Publisher Batch",
            "description": "Promote reviewed resources in bulk. Public examples use `Patient/_batch`.",
        },
        {
            "name": "9. Legacy Endpoints",
            "description": "Deprecated aliases from previous route conventions, kept temporarily for compatibility.",
        },
        {
            "name": "OAuth Token Exchange",
            "description": (
                "Issue a short-lived DataConv access token (Bearer) by presenting an OIDC `id_token` "
                "(and optionally a `vp_token` or an API key).\n\n"
                "The resulting `access_token` must be passed as `Authorization: Bearer <token>` on all "
                "DIDComm endpoints when `DEMO_MODE=false`.\n\n"
                "Alias `/oauth/token` accepts the same body for OAuth 2.0 client compatibility.\n\n"
                "**ICA clearing-house**: pre-validation via ICA `/clearinghouse/verify` is not yet "
                "implemented — see TODO in `TokenExchangeManager.exchange()`."
            ),
        },
        {
            "name": "1.3 Tenant Auth API Keys",
            "description": "Tenant controller API for creating, disabling and removing per-email API keys with granular scopes.",
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
    exchange_operation = rewritten_paths.get(EXCHANGE_PATH, {}).get("post")
    oauth_token_operation = rewritten_paths.get(OAUTH_TOKEN_PATH, {}).get("post")
    api_key_create_operation = rewritten_paths.get(API_KEY_CREATE_PATH, {}).get("post")
    api_key_disable_operation = rewritten_paths.get(API_KEY_DISABLE_PATH, {}).get("post")
    api_key_remove_operation = rewritten_paths.get(API_KEY_REMOVE_PATH, {}).get("post")

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

    _configure_exchange_operation(exchange_operation)
    _configure_exchange_operation(oauth_token_operation)

    _configure_tenant_api_key_operation(
        api_key_create_operation,
        summary="Create tenant-scoped API key policy",
        request_example={
            "data": [
                {
                    "resource": {
                        "@context": "https://schema.org",
                        "@type": "UpdateAction",
                        "agent": {"email": "alice@example.com"},
                        "target": "publisher/cds-es/v1/animal-care/vates-a00000001/dataset/*/*/_upload",
                        "scope": ["dataconv.upload"],
                        "instrument": {"permission": [{"action": "update"}]},
                        "actionStatus": "active",
                    }
                }
            ]
        },
        response_example={
            "data": [
                {
                    "resource": {
                        "@context": "https://schema.org",
                        "@type": "Person",
                        "identifier": "api-key-uuid-1",
                        "actionStatus": "active",
                        "agent": {"sameAs": "zMockedSameAsHash"},
                        "target": "publisher/cds-es/v1/animal-care/vates-a00000001/dataset/*/*/_upload",
                        "scope": ["dataconv.upload"],
                        "instrument": {"permission": [{"action": "update"}]},
                        "tenantId": "vates-a00000001",
                        "expiresAt": "",
                        "apiKey": "dck_abc",
                    }
                }
            ]
        },
    )
    _configure_tenant_api_key_operation(
        api_key_disable_operation,
        summary="Disable tenant-scoped API key policy",
        request_example={
            "data": [
                {
                    "resource": {
                        "@context": "https://schema.org",
                        "@type": "UpdateAction",
                        "identifier": "api-key-uuid-1",
                    }
                }
            ]
        },
        response_example={
            "data": [
                {
                    "resource": {
                        "@context": "https://schema.org",
                        "@type": "Person",
                        "identifier": "api-key-uuid-1",
                        "actionStatus": "disabled",
                        "agent": {"sameAs": "zMockedSameAsHash"},
                        "target": "publisher/cds-es/v1/animal-care/vates-a00000001/dataset/*/*/_upload",
                        "scope": ["dataconv.upload"],
                        "instrument": {},
                        "tenantId": "vates-a00000001",
                        "expiresAt": "",
                    }
                }
            ]
        },
    )
    _configure_tenant_api_key_operation(
        api_key_remove_operation,
        summary="Remove tenant-scoped API key policy",
        request_example={
            "data": [
                {
                    "resource": {
                        "@context": "https://schema.org",
                        "@type": "UpdateAction",
                        "identifier": "api-key-uuid-1",
                    }
                }
            ]
        },
        response_example={
            "data": [
                {
                    "resource": {
                        "@context": "https://schema.org",
                        "@type": "Person",
                        "identifier": "api-key-uuid-1",
                        "actionStatus": "disabled",
                        "agent": {"sameAs": "zMockedSameAsHash"},
                        "target": "publisher/cds-es/v1/animal-care/vates-a00000001/dataset/*/*/_upload",
                        "scope": ["dataconv.upload"],
                        "instrument": {},
                        "tenantId": "vates-a00000001",
                        "expiresAt": "",
                        "removed": True,
                    }
                }
            ]
        },
    )

    for operation in (
        create_operation,
        create_response_operation,
        upload_operation,
        upload_response_operation,
        patch_operation,
        batch_operation,
        search_operation,
        api_key_create_operation,
        api_key_disable_operation,
        api_key_remove_operation,
    ):
        if isinstance(operation, dict):
            drop_422_validation_response(operation)


def _configure_exchange_operation(operation: dict[str, Any] | None) -> None:
    if not isinstance(operation, dict):
        return
    # Exchange endpoint is public — no Bearer required to call it (it issues the token)
    operation["security"] = []
    operation["requestBody"] = {
        "required": True,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/TokenExchangeRequest"},
                "examples": {
                    "idTokenExchange": {
                        "summary": "Exchange OIDC id_token for DataConv access token",
                        "value": {
                            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                            "subject_token": "<OIDC id_token JWT>",
                            "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
                            "scope": "dataconv.upload dataconv.search",
                        },
                    },
                    "apiKeyExchange": {
                        "summary": "Exchange OIDC id_token + API key for DataConv access token",
                        "value": {
                            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                            "subject_token": "<OIDC id_token JWT>",
                            "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
                            "api_key": "<tenant-api-key>",
                            "organization": "<tenant-id>",
                            "scope": "dataconv.upload dataconv.search",
                        },
                    },
                },
            },
            "application/x-www-form-urlencoded": {
                "schema": {"$ref": "#/components/schemas/TokenExchangeRequest"},
            },
        },
    }
    operation.setdefault("responses", {})["200"] = {
        "description": "Access token issued. Pass as `Authorization: Bearer <access_token>` on all DIDComm endpoints.",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/TokenExchangeResponse"},
                "example": {
                    "access_token": "<JWT>",
                    "token_type": "Bearer",
                    "expires_in": 900,
                    "scope": "dataconv.upload dataconv.search",
                },
            }
        },
    }
    drop_422_validation_response(operation)
    responses = operation.setdefault("responses", {})
    responses["400"] = {"description": "Invalid request or unsupported grant type."}
    responses["401"] = {"description": "subject_token invalid, expired, or issuer not trusted."}


def _configure_tenant_api_key_operation(
    operation: dict[str, Any] | None,
    *,
    summary: str,
    request_example: dict[str, Any],
    response_example: dict[str, Any],
) -> None:
    if not isinstance(operation, dict):
        return
    operation["security"] = [{"BearerAuth": []}]
    operation["summary"] = summary
    set_path_param_description(
        operation,
        "tenant-id",
        "Stable organization identifier (`taxId` / `VAT`) used as tenant id.",
    )
    operation["requestBody"] = {
        "required": True,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/TenantApiKeyActionRequest"},
                "example": request_example,
            }
        },
    }
    operation.setdefault("responses", {})["200"] = {
        "description": "Tenant API key registry updated.",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/TenantApiKeyActionResponse"},
                "example": response_example,
            }
        },
    }
    operation.setdefault("responses", {})["401"] = {"description": "Missing or invalid Bearer token."}
    operation.setdefault("responses", {})["403"] = {"description": "Missing `dataconv.tenant.keys.manage` scope or tenant mismatch."}
    operation.setdefault("responses", {})["404"] = {"description": "API key entry not found."}
