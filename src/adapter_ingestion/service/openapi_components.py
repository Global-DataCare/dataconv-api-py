# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any


def install_components(schema: dict[str, Any]) -> None:
    components = schema.setdefault("components", {})
    if not isinstance(components, dict):
        components = {}
        schema["components"] = components

    security_schemes = components.setdefault("securitySchemes", {})
    if not isinstance(security_schemes, dict):
        security_schemes = {}
        components["securitySchemes"] = security_schemes
    security_schemes["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "Optional bearer token used as `id_token` fallback.\n\n"
            "Use an identity token issued by a recognized identity provider "
            "(IdP, for example Google, Microsoft Entra ID, eIDAS, or equivalent), "
            "with the audience expected by this API.\n\n"
            "Examples:\n"
            "- Demo (`PRECONV_AUTH_MODE=parse-only`): `Bearer demo-token`.\n"
            "- Production (`verify-*` modes): `Bearer <JWT id_token>`.\n\n"
            "Click Authorize in Swagger and paste `Bearer <token>`."
        ),
    }

    schemas = components.setdefault("schemas", {})
    if not isinstance(schemas, dict):
        schemas = {}
        components["schemas"] = schemas

    schemas.update(_core_schemas())
    schemas.update(_config_schemas())
    schemas.update(_conversion_schemas())


def _core_schemas() -> dict[str, Any]:
    return {
        "OperationOutcome": {
            "type": "object",
            "required": ["resourceType", "issue"],
            "properties": {
                "resourceType": {"type": "string", "example": "OperationOutcome"},
                "issue": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["severity", "code", "diagnostics"],
                        "properties": {
                            "severity": {"type": "string", "example": "error"},
                            "code": {"type": "string", "example": "invalid"},
                            "diagnostics": {"type": "string"},
                        },
                    },
                },
            },
        },
        "BundleApiErrorBody": {
            "type": "object",
            "required": ["resourceType", "data", "total", "issues"],
            "properties": {
                "resourceType": {"type": "string", "enum": ["Bundle"]},
                "data": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "total": {"type": "integer", "example": 0},
                "issues": {"$ref": "#/components/schemas/OperationOutcome"},
            },
            "additionalProperties": False,
            "example": {
                "resourceType": "Bundle",
                "data": [],
                "total": 0,
                "issues": {
                    "resourceType": "OperationOutcome",
                    "issue": [
                        {
                            "severity": "error",
                            "code": "invalid",
                            "diagnostics": "thid is required in DIDComm payload",
                        }
                    ],
                },
            },
        },
        "DidcommEarlyErrorResponse": {
            "type": "object",
            "required": ["iss", "aud", "thid", "type", "body"],
            "properties": {
                "iss": {"type": "string", "description": "Service DID emitting the error response."},
                "aud": {"type": "string", "description": "Audience DID when available; empty string otherwise."},
                "thid": {"type": "string", "description": "Thread id when available; empty string otherwise."},
                "type": {"type": "string", "enum": ["application/bundle-api+json"]},
                "body": {"$ref": "#/components/schemas/BundleApiErrorBody"},
            },
            "additionalProperties": False,
            "example": {
                "iss": "did:web:globaldatacare.es",
                "aud": "",
                "thid": "",
                "type": "application/bundle-api+json",
                "body": {
                    "resourceType": "Bundle",
                    "data": [],
                    "total": 0,
                    "issues": {
                        "resourceType": "OperationOutcome",
                        "issue": [
                            {
                                "severity": "error",
                                "code": "invalid",
                                "diagnostics": "request validation failed",
                            }
                        ],
                    },
                },
            },
        },
    }


def _config_schemas() -> dict[str, Any]:
    return {
        "SchemaConfig": {
            "type": "object",
            "properties": {
                "headerRowIndex": {"type": "integer", "example": 1},
                "fieldMap": {
                    "type": "object",
                    "properties": {
                        "section": {"type": "string", "example": "SECCION"},
                        "family": {"type": "string", "example": "FAMILIA"},
                        "subfamily": {"type": "string", "example": "SUBFAMILIA"},
                        "concept": {"type": "string", "example": "CONCEPTO"},
                        "subjectId": {"type": "string", "example": "HISTORIA_ID"},
                        "subject-id": {"type": "string", "example": "HISTORIA_ID"},
                        "personal-id": {"type": "string", "example": "DNI"},
                        "owner": {"type": "string", "example": "PROPIETARIO"},
                        "ownerId": {"type": "string", "example": "NIF_PROPIETARIO"},
                        "species": {"type": "string", "example": "ESPECIE"},
                        "breed": {"type": "string", "example": "RAZA"},
                        "genderStatus": {"type": "string", "example": "ESTADO_REPRODUCTIVO"},
                        "sourceId": {"type": "string", "example": "IDARTICULO"},
                        "date": {"type": "string", "example": "FECHA"},
                        "time": {"type": "string", "example": "HORA"},
                    },
                    "additionalProperties": False,
                },
                "fieldDefaults": {"type": "object", "additionalProperties": {"type": "string"}, "example": {}},
                "allowedSections": {"type": "array", "items": {"type": "string"}},
                "excludedSections": {"type": "array", "items": {"type": "string"}},
                "excludedSectionFamilies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "example": ["clinica:vacunas"],
                },
                "speciesContains": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "contains": {"type": "string", "example": "Perro"},
                            "value": {"type": "string", "example": "Perro"},
                        },
                        "required": ["contains"],
                        "additionalProperties": False,
                    },
                },
                "ownerPublicRules": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean", "example": True},
                        "containsAny": {"type": "array", "items": {"type": "string"}, "example": ["ayuntamiento", "cabildo"]},
                        "excludeContainsAny": {"type": "array", "items": {"type": "string"}, "example": ["S.L.", "S.A."]},
                        "publicIdPrefixes": {"type": "array", "items": {"type": "string"}, "example": ["P", "Q", "S"]},
                        "identifierRegex": {"type": "string", "example": "^(?:[A-Z]\\\\d{7}[A-Z0-9]|\\\\d{8}[A-Z])$"},
                        "relationship": {"type": "string", "example": "organization-owner"},
                    },
                    "additionalProperties": False,
                },
                "loincBySectionFamily": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "example": {"clinica:laboratorio": "30954-2"},
                },
                "encounterClassBySectionFamily": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "example": {"clinica:laboratorio": "AMB"},
                },
                "encounterServiceTypeBySectionFamily": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "example": {"clinica:laboratorio": "http://terminology.hl7.org/CodeSystem/service-type|581"},
                },
            },
            "additionalProperties": False,
            "example": {
                "headerRowIndex": 1,
                "fieldMap": {
                    "section": "SECCION",
                    "family": "FAMILIA",
                    "subfamily": "SUBFAMILIA",
                    "concept": "CONCEPTO",
                    "subjectId": "HISTORIA_ID",
                    "owner": "PROPIETARIO",
                    "ownerId": "NIF_PROPIETARIO",
                    "species": "ESPECIE",
                    "breed": "RAZA",
                    "genderStatus": "ESTADO_REPRODUCTIVO",
                    "sourceId": "IDARTICULO",
                    "date": "FECHA",
                    "time": "HORA",
                },
                "fieldDefaults": {},
                "allowedSections": ["clinica"],
                "excludedSections": [],
                "excludedSectionFamilies": ["clinica:vacunas"],
                "speciesContains": [{"contains": "Perro", "value": "Perro"}, {"contains": "Gato", "value": "Gato"}],
                "ownerPublicRules": {
                    "enabled": True,
                    "containsAny": ["ayuntamiento", "cabildo"],
                    "excludeContainsAny": ["S.L.", "S.A."],
                    "publicIdPrefixes": ["P", "Q", "S"],
                    "identifierRegex": "^(?:[A-Z]\\\\d{7}[A-Z0-9]|\\\\d{8}[A-Z])$",
                    "relationship": "organization-owner",
                },
                "loincBySectionFamily": {"clinica:laboratorio": "30954-2"},
                "encounterClassBySectionFamily": {"clinica:*": "AMB"},
                "encounterServiceTypeBySectionFamily": {},
            },
        },
        "SpeciesFhirConfig": {
            "type": "object",
            "properties": {
                "system": {"type": "string", "example": "http://hl7.org/fhir/target-species"},
                "codes": {"type": "object", "additionalProperties": {"type": "string"}},
            },
            "additionalProperties": False,
            "example": {
                "system": "http://hl7.org/fhir/target-species",
                "codes": {"100000108988": "Dogs", "100000109056": "Cats"},
            },
        },
        "RuntimeDefaultsConfig": {
            "type": "object",
            "properties": {
                "language": {"type": "string", "example": "es-ES"},
                "dataUse": {"type": "string", "enum": ["secondary", "individual"], "example": "secondary"},
                "subjectKind": {"type": "string", "example": "animal"},
                "subjectDidPrefix": {"type": "string", "example": "did:web:clinic.example"},
                "includeFields": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
            "example": {
                "language": "es-ES",
                "dataUse": "secondary",
                "subjectKind": "animal",
                "subjectDidPrefix": "did:web:clinic.example",
                "includeFields": ["FECHA", "CONCEPTO", "SECCION", "FAMILIA", "SUBFAMILIA", "SUBJECT_ID", "ESPECIE"],
            },
        },
        "TenantAdapterConfigPayload": {
            "type": "object",
            "properties": {
                "mappingConfig": {"$ref": "#/components/schemas/SchemaConfig"},
                "speciesFhir": {"$ref": "#/components/schemas/SpeciesFhirConfig"},
                "speciesLocalToFhirCode": {"type": "object", "additionalProperties": {"type": "string"}},
                "runtimeDefaults": {"$ref": "#/components/schemas/RuntimeDefaultsConfig"},
            },
            "additionalProperties": False,
            "example": {
                "mappingConfig": {
                    "headerRowIndex": 1,
                    "fieldMap": {
                        "section": "SECCION",
                        "family": "FAMILIA",
                        "subfamily": "SUBFAMILIA",
                        "concept": "CONCEPTO",
                        "subjectId": "HISTORIA_ID",
                        "owner": "PROPIETARIO",
                        "ownerId": "NIF_PROPIETARIO",
                        "species": "ESPECIE",
                        "date": "FECHA",
                        "time": "HORA",
                    },
                    "excludedSectionFamilies": ["clinica:vacunas"],
                    "loincBySectionFamily": {"clinica:laboratorio": "30954-2"},
                    "encounterClassBySectionFamily": {"clinica:*": "AMB"},
                },
                "speciesLocalToFhirCode": {"CANINA": "100000108988", "FELINA": "100000109056"},
                "runtimeDefaults": {
                    "language": "es-ES",
                    "dataUse": "secondary",
                    "subjectKind": "animal",
                    "subjectDidPrefix": "did:web:clinic.example",
                    "includeFields": ["FECHA", "CONCEPTO", "SECCION", "FAMILIA", "SUBFAMILIA", "SUBJECT_ID", "ESPECIE"],
                },
            },
        },
        "DidcommNewOrgConfigEntry": {
            "type": "object",
            "required": ["softwareId"],
            "properties": {
                "softwareId": {"type": "string", "example": "qvet-v1.0"},
                "softwareVersion": {"type": "string", "example": "v1.0"},
                "updatedBy": {"type": "string"},
                "config": {"$ref": "#/components/schemas/TenantAdapterConfigPayload"},
            },
            "additionalProperties": False,
        },
        "DidcommNewOrgConfigCreateRequest": {
            "type": "object",
            "required": ["iss", "thid", "type", "iat", "exp"],
            "properties": {
                "iss": {"type": "string"},
                "aud": {"type": "string"},
                "thid": {"type": "string"},
                "jti": {"type": "string"},
                "iat": {"type": "integer", "format": "int64"},
                "exp": {"type": "integer", "format": "int64"},
                "type": {"type": "string", "example": "https://didcomm.org/plaintext/2.0/message"},
                "vp_token": {"type": "string"},
                "id_token": {"type": "string"},
                "data": {"type": "array", "items": {"$ref": "#/components/schemas/DidcommNewOrgConfigEntry"}},
                "body": {"type": "object", "additionalProperties": True},
            },
            "additionalProperties": False,
        },
        "DidcommNewOrgConfigPollRequest": {
            "type": "object",
            "required": ["iss", "thid", "type", "iat", "exp"],
            "properties": {
                "iss": {"type": "string"},
                "aud": {"type": "string"},
                "thid": {"type": "string"},
                "jti": {"type": "string"},
                "iat": {"type": "integer", "format": "int64"},
                "exp": {"type": "integer", "format": "int64"},
                "type": {"type": "string", "example": "https://didcomm.org/plaintext/2.0/message"},
                "vp_token": {"type": "string"},
                "id_token": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "DidcommNewOrgConfigPollResponse": {
            "type": "object",
            "required": ["thid", "iss", "aud", "type", "iat", "exp", "body"],
            "properties": {
                "jti": {"type": "string"},
                "thid": {"type": "string"},
                "iss": {"type": "string"},
                "aud": {"type": "string"},
                "type": {"type": "string"},
                "iat": {"type": "integer", "format": "int64"},
                "exp": {"type": "integer", "format": "int64"},
                "body": {
                    "type": "object",
                    "required": ["resourceType", "type", "data"],
                    "properties": {
                        "resourceType": {"type": "string", "enum": ["Bundle"]},
                        "type": {"type": "string", "enum": ["batch-response"]},
                        "issues": {"$ref": "#/components/schemas/OperationOutcome"},
                        "data": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string"},
                                    "resource": {"type": "object", "additionalProperties": True},
                                    "response": {
                                        "type": "object",
                                        "required": ["status", "outcome"],
                                        "properties": {
                                            "status": {"type": "string"},
                                            "outcome": {"$ref": "#/components/schemas/OperationOutcome"},
                                        },
                                        "additionalProperties": True,
                                    },
                                },
                                "required": ["response"],
                                "additionalProperties": True,
                            },
                        },
                        "total": {"type": "integer"},
                    },
                    "additionalProperties": True,
                },
            },
            "additionalProperties": True,
        },
    }


def _conversion_schemas() -> dict[str, Any]:
    return {
        "DidcommUploadMultipartRequest": {
            "type": "object",
            "required": ["iss", "thid", "type", "iat", "exp"],
            "properties": {
                "file": {"type": "string", "format": "binary"},
                "iss": {"type": "string"},
                "aud": {"type": "string"},
                "thid": {"type": "string"},
                "jti": {"type": "string"},
                "iat": {"type": "integer", "format": "int64"},
                "exp": {"type": "integer", "format": "int64"},
                "type": {"type": "string", "example": "https://didcomm.org/plaintext/2.0/message"},
                "vp_token": {"type": "string"},
                "id_token": {"type": "string"},
                "send": {"type": "boolean", "default": False},
            },
            "additionalProperties": False,
        },
        "DidcommBundleBody": {
            "type": "object",
            "required": ["resourceType", "data"],
            "properties": {
                "resourceType": {"type": "string", "enum": ["Bundle"]},
                "type": {"type": "string", "example": "batch"},
                "data": {"type": "array", "items": {"type": "object", "additionalProperties": True}, "example": []},
                "total": {"type": "integer", "example": 0},
            },
            "additionalProperties": True,
            "example": {"resourceType": "Bundle", "type": "batch", "data": [], "total": 0},
        },
        "DidcommAttachmentData": {
            "type": "object",
            "properties": {
                "base64": {"type": "string", "description": "Excel file encoded as base64."},
                "links": {
                    "type": "array",
                    "description": "Exactly one HTTP(S) URL from which the API downloads the source file.",
                    "items": {"type": "string"},
                    "maxItems": 1,
                },
            },
            "additionalProperties": True,
        },
        "DidcommAttachment": {
            "type": "object",
            "required": ["id", "data"],
            "properties": {
                "id": {"type": "string"},
                "media_type": {
                    "type": "string",
                    "example": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                },
                "filename": {"type": "string", "example": "exampleQvetES.xlsx"},
                "data": {"$ref": "#/components/schemas/DidcommAttachmentData"},
            },
            "additionalProperties": True,
        },
        "DidcommUploadDidcommPlaintextRequest": {
            "type": "object",
            "required": ["iss", "thid", "type", "iat", "exp", "body", "attachments"],
            "properties": {
                "iss": {"type": "string"},
                "aud": {"type": "string"},
                "thid": {"type": "string"},
                "jti": {"type": "string"},
                "iat": {"type": "integer", "format": "int64"},
                "exp": {"type": "integer", "format": "int64"},
                "type": {"type": "string", "example": "https://didcomm.org/plaintext/2.0/message"},
                "vp_token": {"type": "string"},
                "id_token": {"type": "string"},
                "send": {"type": "boolean", "default": False},
                "body": {"$ref": "#/components/schemas/DidcommBundleBody"},
                "attachments": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/DidcommAttachment"},
                    "maxItems": 1,
                    "description": "Current public profile accepts exactly one attachment per upload request.",
                },
            },
            "additionalProperties": False,
        },
        "DidcommUploadResponseRequest": {
            "type": "object",
            "required": ["iss", "thid", "type", "iat", "exp"],
            "properties": {
                "iss": {"type": "string"},
                "aud": {"type": "string"},
                "thid": {"type": "string"},
                "jti": {"type": "string"},
                "iat": {"type": "integer", "format": "int64"},
                "exp": {"type": "integer", "format": "int64"},
                "type": {"type": "string", "example": "https://didcomm.org/plaintext/2.0/message"},
                "vp_token": {"type": "string"},
                "id_token": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "DidcommPollResponse": {
            "type": "object",
            "required": ["thid", "type", "body"],
            "properties": {
                "jti": {"type": "string"},
                "thid": {"type": "string"},
                "iss": {"type": "string"},
                "aud": {"type": "string"},
                "type": {"type": "string"},
                "iat": {"type": "integer", "format": "int64"},
                "exp": {"type": "integer", "format": "int64"},
                "attachments": {"type": "array", "items": {"$ref": "#/components/schemas/DidcommAttachment"}},
                "body": {
                    "type": "object",
                    "required": ["resourceType", "type", "issues", "data", "total"],
                    "properties": {
                        "resourceType": {"type": "string", "enum": ["Bundle"]},
                        "type": {"type": "string", "enum": ["batch-response"]},
                        "issues": {"$ref": "#/components/schemas/OperationOutcome"},
                        "data": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string", "example": "ConversionResult"},
                                    "resource": {"type": "object", "additionalProperties": True},
                                    "response": {
                                        "type": "object",
                                        "required": ["status", "outcome"],
                                        "properties": {
                                            "status": {"type": "string", "example": "200"},
                                            "queuePosition": {
                                                "type": "integer",
                                                "minimum": 1,
                                                "description": "Best-effort queue position when conversion is still queued.",
                                            },
                                            "outcome": {"$ref": "#/components/schemas/OperationOutcome"},
                                        },
                                        "additionalProperties": True,
                                    },
                                },
                                "required": ["response"],
                                "additionalProperties": True,
                            },
                        },
                        "total": {"type": "integer", "example": 1},
                    },
                    "additionalProperties": True,
                },
            },
            "additionalProperties": True,
        },
        "DidcommPromotionRequest": {
            "type": "object",
            "required": ["iss", "thid", "type", "iat", "exp"],
            "properties": {
                "iss": {"type": "string", "example": "did:web:clinic.example:employee:it:loader"},
                "aud": {"type": "string"},
                "thid": {"type": "string", "example": "up-qvet-20260315-001"},
                "jti": {"type": "string"},
                "iat": {"type": "integer", "format": "int64"},
                "exp": {"type": "integer", "format": "int64"},
                "type": {"type": "string", "example": "https://didcomm.org/plaintext/2.0/message"},
                "vp_token": {"type": "string"},
                "id_token": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "DidcommPromotionResponse": {
            "type": "object",
            "required": ["type", "thid", "body"],
            "properties": {
                "type": {"type": "string", "example": "https://didcomm.org/plaintext/2.0/message"},
                "thid": {"type": "string", "example": "up-qvet-20260315-001"},
                "body": {
                    "type": "object",
                    "required": ["status", "promotedCount", "message"],
                    "properties": {
                        "status": {"type": "string", "example": "success"},
                        "promotedCount": {"type": "integer", "example": 14},
                        "message": {
                            "type": "string",
                            "example": "Promoted 14 resources to userSelected=false",
                        },
                    },
                    "additionalProperties": True,
                },
            },
            "additionalProperties": True,
        },
        "TenantScopedFhirSearchRequest": {
            "type": "object",
            "additionalProperties": {"type": "string"},
            "example": {
                "userselected": "false",
                "date": "ge2026-01-01",
            },
        },
        "TenantScopedFhirSearchResponse": {
            "type": "object",
            "required": ["resourceType", "type", "total", "entry"],
            "properties": {
                "resourceType": {"type": "string", "enum": ["Bundle"]},
                "type": {"type": "string", "enum": ["searchset"]},
                "total": {"type": "integer", "example": 4},
                "entry": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "fullUrl": {"type": "string", "example": "urn:uuid:doc-1"},
                            "resource": {"type": "object", "additionalProperties": True},
                        },
                        "additionalProperties": True,
                    },
                },
            },
            "additionalProperties": True,
            "example": {
                "resourceType": "Bundle",
                "type": "searchset",
                "total": 1,
                "entry": [
                    {
                        "fullUrl": "urn:uuid:doc-1",
                        "resource": {
                            "resourceType": "DocumentReference",
                            "id": "doc-1",
                            "docStatus": "preliminary",
                            "date": "2026-01-07",
                            "meta": {
                                "claims": {
                                    "DocumentReference.userSelected": "false",
                                    "DocumentReference.docStatus": "preliminary",
                                    "DocumentReference.date": "2026-01-07",
                                }
                            },
                        },
                    }
                ],
            },
        },
    }
