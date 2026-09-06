# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from .. import __version__
from .openapi_constants import (
    API_KEY_CREATE_PATH,
    API_KEY_DISABLE_PATH,
    API_KEY_REMOVE_PATH,
    API_KEY_SEARCH_PATH,
    AUTH_CODE_RESPONSE_PATH,
    AUTH_CODE_PATH,
    AUTH_DCR_RESPONSE_PATH,
    AUTH_DCR_PATH,
    AUTH_EXCHANGE_RESPONSE_PATH,
    AUTH_EXCHANGE_PATH,
    AUTH_TOKEN_RESPONSE_PATH,
    AUTH_TOKEN_PATH,
    BATCH_PATH,
    CREATE_PATH,
    CREATE_RESPONSE_PATH,
    CONTROLLER_EXCHANGE_PATH,
    CONTROLLER_EXCHANGE_RESPONSE_PATH,
    EXCHANGE_PATH,
    LEGACY_UPLOAD_PATH,
    LEGACY_UPLOAD_RESPONSE_PATH,
    OAUTH_TOKEN_PATH,
    PATCH_PATH,
    PROFESSIONAL_RESEARCH_EXCHANGE_PATH,
    SEARCH_PATH,
    UPLOAD_PATH,
    UPLOAD_RESPONSE_PATH,
)
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
        info["version"] = __version__
        info["description"] = (
            "Public DIDComm/FAPI contract for tenant configuration and conversion jobs.\n\n"
            "**Functional groups**\n\n"
            "- 1.1 Controller Auth Exchange: `/publisher/cds-{jurisdiction}/v1/{sector}/organization/dataspace/auth/_exchange`\n"
            "- 1.2 Controller API Key Provisioning: `/publisher/cds-{jurisdiction}/v1/{sector}/api-key/org.schema/action/_*`\n"
            "- 2.1 Identity Auth DCR: `/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/identity/auth/_dcr`\n"
            "- 2.2 Identity Auth PKCE Code: `/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/identity/auth/_code`\n"
            "- 2.3 Identity Auth PKCE Token: `/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/identity/auth/_token`\n"
            "- 2.4 Identity Auth Exchange: `/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/identity/auth/_exchange`\n"
            "- 2.5 Professional Research Auth Exchange: `/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/professional/research/auth/_exchange`\n"
            "- 3.1 Publisher Config Request: `_create`\n"
            "- 3.2 Publisher Config Response: `_create-response`\n"
            "- 4.1 Publisher Upload Request: `_upload`\n"
            "- 4.2 Publisher Upload Response: `_upload-response`\n"
            "- 4.3 Publisher Patch: `_patch`\n"
            "- 4.4 Publisher Dataset Search: `_search`\n"
            "- 4.5 Publisher Batch: `_batch`\n"
            "- 9.x Legacy aliases: deprecated compatibility routes\n\n"
            "**Identity model**\n\n"
            "Requester identity is extracted from DIDComm `iss`.\n\n"
            "**Authentication**\n\n"
            "- V2 flow: business endpoints use `Authorization: Bearer <access_token>`\n"
            "- `id_token` is used in identity/auth exchange steps, not in business DIDComm payloads\n"
            "- `DEMO_MODE=true`: signature validation is bypassed; temporary legacy payload token fields may still be accepted for compatibility\n"
            "- `DEMO_MODE=false`: Bearer token required and fully validated\n\n"
            "**SDK Auth Sequence (backend)**\n\n"
            "1. `POST /publisher/cds-{jurisdiction}/v1/{sector}/organization/dataspace/auth/_exchange` then poll `_exchange-response`\n"
            "2. `POST /publisher/cds-{jurisdiction}/v1/{sector}/api-key/org.schema/action/_create` (optional API-key provisioning)\n"
            "3. `POST .../{tenant-id}/identity/auth/_dcr` then poll `_dcr-response`\n"
            "4. `POST .../{tenant-id}/identity/auth/_code` then poll `_code-response`\n"
            "5. `POST .../{tenant-id}/identity/auth/_token` then poll `_token-response`\n"
            "6. `POST .../{tenant-id}/identity/auth/_exchange` then poll `_exchange-response`\n\n"
            "**API Key Binding Model**\n\n"
            "- Step 1 (`1.2 _create`): controller provisions API key policy for a backend/service principal. Result is `pending_dcr`.\n"
            "- Step 2 (`2.1 _dcr`): service/device registers using `client_id` (same value as the API key in backend SDK profile) + controller JWK (`meta.jws.protected.jwk`) to bind cryptographic identity.\n"
            "- Only after successful DCR binding should SDK continue with PKCE (`_code`, `_token`) and final tenant exchange (`_exchange`).\n\n"
            "**Operational notes**\n\n"
            "- Terminal job responses expire after `PRECONV_JOB_RESULT_TTL_SECONDS`\n"
            "- Deployment probe endpoint `/healthz` is intentionally excluded from this contract"
        )

    schema["tags"] = [
        {
            "name": "1.1 Controller Auth Exchange",
            "description": "Bootstrap exchange before tenant-scoped identity flows.",
        },
        {
            "name": "1.2 Controller API Key Provisioning",
            "description": "Create/disable/remove API keys for organization from controller token context.",
        },
        {
            "name": "2.1 Identity Auth DCR",
            "description": "Dynamic client registration in tenant-scoped identity flow.",
        },
        {
            "name": "2.2 Identity Auth PKCE Code",
            "description": "PKCE code request in tenant-scoped identity flow.",
        },
        {
            "name": "2.3 Identity Auth PKCE Token",
            "description": "PKCE token request in tenant-scoped identity flow.",
        },
        {
            "name": "2.4 Identity Auth Exchange",
            "description": "Final tenant-scoped identity exchange step.",
        },
        {
            "name": "2.5 Professional Research Auth Exchange",
            "description": "Offline exchange of one GW-signed, professional and ResearchStudy-scoped SMART token.",
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
            "description": "Promote a reviewed conversion thread. Public examples use `Composition/_patch`.",
        },
        {
            "name": "4.4 Publisher Dataset Search",
            "description": "Tenant-scoped dataset search endpoint (FHIR-backed implementation).",
        },
        {
            "name": "4.5 Publisher Batch",
            "description": "Promote reviewed resources in bulk. Public examples use `Patient/_batch`.",
        },
        {
            "name": "9. Legacy Endpoints",
            "description": "Deprecated aliases from previous route conventions, kept temporarily for compatibility.",
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
    legacy_upload_operation = rewritten_paths.get(LEGACY_UPLOAD_PATH, {}).get("post")
    legacy_upload_response_operation = rewritten_paths.get(LEGACY_UPLOAD_RESPONSE_PATH, {}).get("post")
    patch_operation = rewritten_paths.get(PATCH_PATH, {}).get("post")
    batch_operation = rewritten_paths.get(BATCH_PATH, {}).get("post")
    search_operation = rewritten_paths.get(SEARCH_PATH, {}).get("post")
    exchange_operation = rewritten_paths.get(EXCHANGE_PATH, {}).get("post")
    oauth_token_operation = rewritten_paths.get(OAUTH_TOKEN_PATH, {}).get("post")
    professional_research_exchange_operation = rewritten_paths.get(PROFESSIONAL_RESEARCH_EXCHANGE_PATH, {}).get("post")
    controller_exchange_operation = rewritten_paths.get(CONTROLLER_EXCHANGE_PATH, {}).get("post")
    controller_exchange_response_operation = rewritten_paths.get(CONTROLLER_EXCHANGE_RESPONSE_PATH, {}).get("post")
    auth_dcr_operation = rewritten_paths.get(AUTH_DCR_PATH, {}).get("post")
    auth_dcr_response_operation = rewritten_paths.get(AUTH_DCR_RESPONSE_PATH, {}).get("post")
    auth_code_operation = rewritten_paths.get(AUTH_CODE_PATH, {}).get("post")
    auth_code_response_operation = rewritten_paths.get(AUTH_CODE_RESPONSE_PATH, {}).get("post")
    auth_token_operation = rewritten_paths.get(AUTH_TOKEN_PATH, {}).get("post")
    auth_token_response_operation = rewritten_paths.get(AUTH_TOKEN_RESPONSE_PATH, {}).get("post")
    auth_exchange_operation = rewritten_paths.get(AUTH_EXCHANGE_PATH, {}).get("post")
    auth_exchange_response_operation = rewritten_paths.get(AUTH_EXCHANGE_RESPONSE_PATH, {}).get("post")
    api_key_create_operation = rewritten_paths.get(API_KEY_CREATE_PATH, {}).get("post")
    api_key_disable_operation = rewritten_paths.get(API_KEY_DISABLE_PATH, {}).get("post")
    api_key_remove_operation = rewritten_paths.get(API_KEY_REMOVE_PATH, {}).get("post")
    api_key_search_operation = rewritten_paths.get(API_KEY_SEARCH_PATH, {}).get("post")

    if isinstance(create_operation, dict):
        create_operation["tags"] = ["3.1 Publisher Config Request"]
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
        create_response_operation["tags"] = ["3.2 Publisher Config Response"]
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
        upload_operation["tags"] = ["4.1 Publisher Upload Request"]
        upload_operation["security"] = [{"BearerAuth": []}]
        set_path_param_description(
            upload_operation,
            "tenant-id",
            "Stable organization identifier (`taxId` / `VAT`). It appears in both route segments and must match.",
        )
        upload_operation["requestBody"] = {
            "required": True,
            "content": {
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
                "multipart/form-data": {
                    "schema": {"$ref": "#/components/schemas/DidcommUploadMultipartRequest"}
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
        upload_response_operation["tags"] = ["4.2 Publisher Upload Response"]
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

    if isinstance(legacy_upload_operation, dict):
        legacy_upload_operation["tags"] = ["4.1 Publisher Upload Request"]
        legacy_upload_operation["security"] = [{"BearerAuth": []}]
        set_path_param_description(
            legacy_upload_operation,
            "tenant-id",
            "Stable organization identifier (`taxId` / `VAT`). It appears in both route segments and must match.",
        )
        legacy_upload_operation["requestBody"] = {
            "required": True,
            "content": {
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
                "multipart/form-data": {
                    "schema": {"$ref": "#/components/schemas/DidcommUploadMultipartRequest"}
                },
            },
        }
        legacy_upload_responses = legacy_upload_operation.setdefault("responses", {})
        if isinstance(legacy_upload_responses, dict):
            legacy_upload_responses["202"] = {
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
        set_operation_outcome_error_responses(legacy_upload_operation)

    if isinstance(legacy_upload_response_operation, dict):
        legacy_upload_response_operation["tags"] = ["4.2 Publisher Upload Response"]
        legacy_upload_response_operation["security"] = [{"BearerAuth": []}]
        set_path_param_description(
            legacy_upload_response_operation,
            "tenant-id",
            "Stable organization identifier (`taxId` / `VAT`). It appears in both route segments and must match.",
        )
        legacy_upload_response_operation["requestBody"] = {
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
        append_optional_query_thid_parameter(legacy_upload_response_operation)
        legacy_upload_response_responses = legacy_upload_response_operation.setdefault("responses", {})
        if isinstance(legacy_upload_response_responses, dict):
            legacy_upload_response_responses["202"] = {
                "description": "Upload result not ready yet (queued/running). Retry later.",
                "headers": {
                    "Location": {
                        "description": "Same polling endpoint URL.",
                        "schema": {"type": "string"},
                    },
                    "Retry-After": {
                        "description": "Recommended polling delay in seconds.",
                        "schema": {"type": "string", "example": "5"},
                    },
                },
                "content": {
                    "application/didcomm-plain+json": {
                        "schema": {"$ref": "#/components/schemas/DidcommPollResponse"},
                    }
                },
            }
            legacy_upload_response_responses["200"] = {
                "description": "Upload result finished (success/failure) with conversion bundle and diagnostics.",
                "content": {
                    "application/didcomm-plain+json": {
                        "schema": {"$ref": "#/components/schemas/DidcommPollResponse"},
                    }
                },
            }
        set_operation_outcome_error_responses(legacy_upload_response_operation, include_404=True)

    if isinstance(patch_operation, dict):
        patch_operation["tags"] = ["4.3 Publisher Patch"]
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
        batch_operation["tags"] = ["4.5 Publisher Batch"]
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
        search_operation["tags"] = ["4.4 Publisher Dataset Search"]
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

    _configure_auth_dcr_operation(auth_dcr_operation)
    _configure_auth_poll_operation(auth_dcr_response_operation, tag="2.1 Identity Auth DCR", action="_dcr")
    _configure_auth_code_operation(auth_code_operation)
    _configure_auth_poll_operation(auth_code_response_operation, tag="2.2 Identity Auth PKCE Code", action="_code")
    _configure_auth_token_operation(auth_token_operation)
    _configure_auth_poll_operation(auth_token_response_operation, tag="2.3 Identity Auth PKCE Token", action="_token")

    _configure_exchange_operation(exchange_operation, tags=["1.1 Controller Auth Exchange"])
    _configure_exchange_operation(oauth_token_operation, tags=["1.1 Controller Auth Exchange"])
    _configure_professional_research_exchange_operation(professional_research_exchange_operation)
    _configure_exchange_operation(controller_exchange_operation, tags=["1.1 Controller Auth Exchange"], async_mode=True)
    _configure_auth_poll_operation(
        controller_exchange_response_operation, tag="1.1 Controller Auth Exchange", action="_exchange"
    )
    _configure_exchange_operation(auth_exchange_operation, tags=["2.4 Identity Auth Exchange"], async_mode=True)
    _configure_auth_poll_operation(auth_exchange_response_operation, tag="2.4 Identity Auth Exchange", action="_exchange")

    _configure_tenant_api_key_operation(
        api_key_create_operation,
        summary="Create organization API key policy",
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
                        "bindingStatus": "pending_dcr",
                    }
                }
            ]
        },
    )
    _configure_tenant_api_key_operation(
        api_key_disable_operation,
        summary="Disable organization API key policy",
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
        summary="Remove organization API key policy",
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
    _configure_tenant_api_key_search_operation(api_key_search_operation)

    for operation in (
        create_operation,
        create_response_operation,
        upload_operation,
        upload_response_operation,
        legacy_upload_operation,
        legacy_upload_response_operation,
        patch_operation,
        batch_operation,
        search_operation,
        auth_dcr_operation,
        auth_dcr_response_operation,
        auth_code_operation,
        auth_code_response_operation,
        auth_token_operation,
        auth_token_response_operation,
        auth_exchange_operation,
        auth_exchange_response_operation,
        controller_exchange_operation,
        controller_exchange_response_operation,
        exchange_operation,
        oauth_token_operation,
        api_key_create_operation,
        api_key_disable_operation,
        api_key_remove_operation,
        api_key_search_operation,
    ):
        if isinstance(operation, dict):
            drop_422_validation_response(operation)


def _configure_auth_dcr_operation(operation: dict[str, Any] | None) -> None:
    if not isinstance(operation, dict):
        return
    operation["tags"] = ["2.1 Identity Auth DCR"]
    operation["security"] = []
    operation["summary"] = "Dynamic Client Registration (DCR)"
    operation["description"] = (
        "Registers controller client metadata for a tenant-scoped auth session.\n\n"
        "This is the binding step that follows API-key provisioning (`1.2 _create`).\n"
        "Expected lifecycle for SDKs: `pending_dcr` (after `_create`) -> `bound` (after `_dcr-response` terminal success).\n\n"
        "Transport profile:\n"
        "- Content-Type: `application/didcomm-plain+json`\n"
        "- `client_id` at top-level is required and MUST carry the API key value in backend SDK profile\n"
        "- `body` may be `{}`\n"
        "- `meta.jws.protected.jwk` is required for controller key binding\n\n"
        "Async contract: returns `202` with `Location` pointing to `_dcr-response?thid=...`."
    )
    operation["requestBody"] = {
        "required": True,
        "content": {
            "application/didcomm-plain+json": {
                "schema": {"$ref": "#/components/schemas/DidcommAuthRequest"},
                "example": {
                    "thid": "dcr-tenant-acme-001",
                    "type": "application/bundle-api+json",
                    "client_id": "dck_abc",
                    "body": {},
                    "meta": {"jws": {"protected": {"alg": "ES384", "jwk": {"kty": "EC", "crv": "P-384", "x": "<x>", "y": "<y>"}}}},
                },
            }
        },
    }
    operation.setdefault("responses", {})["202"] = {
        "description": "DCR request accepted (binding in progress).",
        "headers": {
            "Location": {"schema": {"type": "string"}},
            "Retry-After": {"schema": {"type": "string", "example": "1"}},
        },
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/AuthAsyncAcceptedResponse"}}},
    }
    operation.setdefault("responses", {})["400"] = {"description": "Invalid DCR payload."}


def _configure_auth_code_operation(operation: dict[str, Any] | None) -> None:
    if not isinstance(operation, dict):
        return
    operation["tags"] = ["2.2 Identity Auth PKCE Code"]
    operation["security"] = []
    operation["summary"] = "PKCE: validate challenge and issue authorization code"
    operation["description"] = (
        "PKCE authorization-code issuance step.\n\n"
        "Required top-level fields:\n"
        "- `client_id`\n"
        "- `code_challenge`\n"
        "- `code_challenge_method` (must be `S256`)\n"
        "- DIDComm metadata in `meta.jws.protected.jwk`\n\n"
        "`body` remains available for DIDComm compatibility and can be `{}`.\n"
        "Async contract: `202` + poll `_code-response` by `thid`."
    )
    operation["requestBody"] = {
        "required": True,
        "content": {
            "application/didcomm-plain+json": {
                "schema": {"$ref": "#/components/schemas/DidcommAuthRequest"},
                "example": {
                    "thid": "pkce-code-001",
                    "type": "application/bundle-api+json",
                    "client_id": "device-client-001",
                    "code_challenge": "<BASE64URL(SHA256(code_verifier))>",
                    "code_challenge_method": "S256",
                    "body": {},
                    "meta": {"jws": {"protected": {"alg": "ES384", "jwk": {"kty": "EC", "crv": "P-384", "x": "<x>", "y": "<y>"}}}},
                },
            }
        },
    }
    operation.setdefault("responses", {})["202"] = {
        "description": "PKCE code request accepted.",
        "headers": {
            "Location": {"schema": {"type": "string"}},
            "Retry-After": {"schema": {"type": "string", "example": "1"}},
        },
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/AuthAsyncAcceptedResponse"}}},
    }
    operation.setdefault("responses", {})["400"] = {"description": "Invalid code request payload."}
    operation.setdefault("responses", {})["401"] = {"description": "Client is not registered via DCR."}


def _configure_auth_token_operation(operation: dict[str, Any] | None) -> None:
    if not isinstance(operation, dict):
        return
    operation["tags"] = ["2.3 Identity Auth PKCE Token"]
    operation["security"] = []
    operation["summary"] = "PKCE: exchange authorization code and verifier for id_token"
    operation["description"] = (
        "PKCE token step: exchange authorization `code` plus `code_verifier` for an `id_token`.\n\n"
        "Required top-level fields:\n"
        "- `client_id`\n"
        "- `code`\n"
        "- `code_verifier`\n"
        "- DIDComm metadata in `meta.jws.protected.jwk`\n\n"
        "`body` can be `{}` in this profile.\n"
        "Async contract: `202` + poll `_token-response` by `thid`."
    )
    operation["requestBody"] = {
        "required": True,
        "content": {
            "application/didcomm-plain+json": {
                "schema": {"$ref": "#/components/schemas/DidcommAuthRequest"},
                "example": {
                    "thid": "pkce-token-001",
                    "type": "application/bundle-api+json",
                    "client_id": "device-client-001",
                    "code": "c2d3f1aa-1d5c-4600-b9b0-973f2f0f2f4e",
                    "code_verifier": "5f6f9758-f78d-4ff4-b099-2fc5e06ff0ad",
                    "body": {},
                    "meta": {"jws": {"protected": {"alg": "ES384", "jwk": {"kty": "EC", "crv": "P-384", "x": "<x>", "y": "<y>"}}}},
                },
            }
        },
    }
    operation.setdefault("responses", {})["202"] = {
        "description": "PKCE token request accepted.",
        "headers": {
            "Location": {"schema": {"type": "string"}},
            "Retry-After": {"schema": {"type": "string", "example": "1"}},
        },
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/AuthAsyncAcceptedResponse"}}},
    }
    operation.setdefault("responses", {})["401"] = {"description": "Invalid/expired code or verifier mismatch."}


def _configure_auth_poll_operation(
    operation: dict[str, Any] | None,
    *,
    tag: str,
    action: str,
) -> None:
    if not isinstance(operation, dict):
        return
    operation["tags"] = [tag]
    operation["security"] = []
    operation["summary"] = f"Poll {action} job status/result"
    operation["description"] = (
        f"Polling endpoint for `{action}` async execution.\n\n"
        "Client must call this endpoint until status is terminal:\n"
        "- `202`: pending, retry using `Retry-After`\n"
        "- `200`: completed, response includes action result payload"
    )
    operation["parameters"] = [
        {
            "name": "thid",
            "in": "query",
            "required": True,
            "schema": {"type": "string"},
            "description": "Thread identifier returned in submit step.",
        }
    ]
    operation["responses"] = {
        "202": {"description": "Pending.", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/AuthAsyncPollResponse"}}}},
        "200": {"description": "Completed.", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/AuthAsyncPollResponse"}}}},
        "404": {"description": "thid not found."},
    }


def _configure_exchange_operation(
    operation: dict[str, Any] | None,
    *,
    tags: list[str] | None = None,
    async_mode: bool = False,
) -> None:
    if not isinstance(operation, dict):
        return
    operation["tags"] = tags or ["1.1 Controller Auth Exchange"]
    # Exchange endpoint is public — no Bearer required to call it (it issues the token)
    operation["security"] = []
    operation["description"] = (
        "Token exchange step (RFC 8693).\n\n"
        "Bootstrap mode: `/publisher/cds-{jurisdiction}/v1/{sector}/organization/dataspace/auth/_exchange` (async).\n"
        "Tenant-scoped mode: `.../identity/auth/_exchange` is asynchronous (`202 + Location`) and polled via `_exchange-response`.\n\n"
        "For DIDComm-plain transport, OAuth fields can be provided at top-level and `body` can be `{}`.\n\n"
        "Exceptional non-confidential client profile is explicit as `api_key_profile=api-key-exception.v1` and must be enabled server-side."
    )
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
                    "apiKeyExceptionExchange": {
                        "summary": "Exceptional API-key-only desktop flow (explicit profile)",
                        "value": {
                            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                            "api_key_profile": "api-key-exception.v1",
                            "api_key": "<tenant-api-key>",
                            "organization": "<tenant-id>",
                            "operational_subject": "did:web:clinic.local:service:excel-uploader",
                            "scope": "dataconv.upload",
                        },
                    },
                },
            },
            "application/x-www-form-urlencoded": {
                "schema": {"$ref": "#/components/schemas/TokenExchangeRequest"},
            },
            "application/didcomm-plain+json": {
                "schema": {"$ref": "#/components/schemas/DidcommAuthRequest"},
            },
        },
    }
    if async_mode:
        operation.setdefault("responses", {})["202"] = {
            "description": "Exchange request accepted.",
            "headers": {
                "Location": {"schema": {"type": "string"}},
                "Retry-After": {"schema": {"type": "string", "example": "1"}},
            },
        }
    else:
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
    responses["401"] = {"description": "subject_token invalid, expired, issuer not trusted, or api-key-exception profile not allowed."}


def _configure_professional_research_exchange_operation(operation: dict[str, Any] | None) -> None:
    if not isinstance(operation, dict):
        return
    operation["tags"] = ["2.5 Professional Research Auth Exchange"]
    operation["security"] = []
    operation["description"] = (
        "RFC 8693 exchange of a GW-signed SMART access token already authorized by DCR and an active "
        "ResearchStudy Consent. DataConv resolves the allowlisted tenant issuer's did:web document, "
        "validates its authentication JWK offline, and requires exact iss/aud, exp/nbf, professional sub, "
        "purpose=HRESCH, study and organization/ResearchSubject.crus?study=... scope. No OIDC id token, "
        "controller VP, or separate researchStudy request field substitutes for the signed claims."
    )
    operation["requestBody"] = {
        "required": True,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ProfessionalResearchTokenExchangeRequest"},
                "example": {
                    "subject_token": "<GW SMART access token>",
                    "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
                },
            },
            "application/x-www-form-urlencoded": {
                "schema": {"$ref": "#/components/schemas/ProfessionalResearchTokenExchangeRequest"},
            },
        },
    }
    operation["responses"] = {
        "200": {
            "description": "Study-bound DataConv token issued.",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ProfessionalResearchTokenExchangeResponse"}}},
        },
        "401": {"description": "The SMART token, DID signature, claims, issuer binding, or active tenant check failed."},
        "403": {"description": "The DataConv tenant is not active for this network, sector and jurisdiction."},
    }
    drop_422_validation_response(operation)


def _configure_tenant_api_key_operation(
    operation: dict[str, Any] | None,
    *,
    summary: str,
    request_example: dict[str, Any],
    response_example: dict[str, Any],
) -> None:
    if not isinstance(operation, dict):
        return
    operation["tags"] = ["1.2 Controller API Key Provisioning"]
    operation["security"] = [{"BearerAuth": []}]
    operation["summary"] = summary
    operation["description"] = (
        "Controller API-key provisioning. Organization/tenant context is resolved from Bearer token claim "
        "`organization` and validated server-side.\n\n"
        "Binding model: `_create` provisions policy and key material (`pending_dcr`). "
        "Device/service binding is completed later via `2.1 identity/auth/_dcr`.\n\n"
        "Atomic policy model: each `data[].resource` is one authorization rule "
        "(`1 rule = 1 consent-like record = 1 ODRL instrument`)."
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
    operation.setdefault("responses", {})["403"] = {"description": "Missing `dataconv.tenant.keys.manage` scope or organization mismatch."}
    operation.setdefault("responses", {})["404"] = {"description": "API key entry not found."}


def _configure_tenant_api_key_search_operation(operation: dict[str, Any] | None) -> None:
    if not isinstance(operation, dict):
        return
    operation["tags"] = ["1.2 Controller API Key Provisioning"]
    operation["security"] = [{"BearerAuth": []}]
    operation["summary"] = "List organization API keys with DCR bindings"
    operation["description"] = (
        "Returns API keys provisioned for the controller organization, enriched with DCR binding information "
        "(clientId, controllerPublicKeyJwk, device metadata).\n\n"
        "Use this endpoint in controller web/app to audit what backend SDK devices have consumed and bound each API key."
    )
    operation["requestBody"] = {
        "required": False,
        "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}},
    }
    operation["responses"] = {
        "200": {
            "description": "API keys and bindings retrieved.",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "resource": {"$ref": "#/components/schemas/TenantApiKeyResource"},
                                        "bindings": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "clientId": {"type": "string"},
                                                    "bindingStatus": {"type": "string", "example": "bound"},
                                                    "boundAt": {"type": "integer", "example": 1760000000},
                                                    "controllerPublicKeyJwk": {"type": "object", "additionalProperties": True},
                                                    "device": {"type": "object", "additionalProperties": True},
                                                },
                                                "additionalProperties": True,
                                            },
                                        },
                                    },
                                    "additionalProperties": True,
                                },
                            }
                        },
                        "additionalProperties": False,
                    }
                }
            },
        },
        "401": {"description": "Missing or invalid Bearer token."},
        "403": {"description": "Missing `dataconv.tenant.keys.manage` scope or organization mismatch."},
    }
