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
            "DataConv access token issued by controller bootstrap exchange `/publisher/cds-{jurisdiction}/v1/{sector}/organization/dataspace/auth/_exchange` and by tenant-scoped identity exchange `.../{tenant-id}/identity/auth/_exchange`.\n\n"
            "1. Bootstrap controller/organization context with controller exchange.\n"
            "2. Copy the returned `access_token`.\n"
            "3. Click Authorize here and paste `Bearer <access_token>`.\n\n"
            "V2 contract: business endpoints authenticate with `Authorization: Bearer <access_token>`.\n"
            "Use `id_token` only in identity/auth exchange steps (`_token` -> `_exchange`).\n"
            "Demo (`DEMO_MODE=true`): signature verification is bypassed; legacy DIDComm `id_token`/`vp_token` payload fields may still be accepted temporarily for compatibility.\n"
            "Production (`DEMO_MODE=false`): Bearer token is required and fully validated."
        ),
    }

    schemas = components.setdefault("schemas", {})
    if not isinstance(schemas, dict):
        schemas = {}
        components["schemas"] = schemas

    schemas.update(_core_schemas())
    schemas.update(_config_schemas())
    schemas.update(_conversion_schemas())
    schemas.update(_exchange_schemas())
    schemas.update(_tenant_api_key_schemas())


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
                        "subject_id": {"type": "string", "example": "HISTORIA_ID"},
                        "personal_id": {"type": "string", "example": "DNI"},
                        "birthyear": {"type": "string", "example": "FECHA_NACIMIENTO"},
                        "birthsex": {"type": "string", "example": "SEXO"},
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
                    "subject_id": "HISTORIA_ID",
                    "birthyear": "FECHA_NACIMIENTO",
                    "birthsex": "SEXO",
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
                "logComposition": {"type": "boolean", "example": False},
                "subjectKind": {"type": "string", "example": "animal"},
                "subjectDidPrefix": {"type": "string", "example": "did:web:clinic.example"},
                "includeFields": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
            "example": {
                "language": "es-ES",
                "dataUse": "secondary",
                "logComposition": False,
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
                        "subject_id": "HISTORIA_ID",
                        "birthyear": "FECHA_NACIMIENTO",
                        "birthsex": "SEXO",
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
                    "logComposition": False,
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
                "vp_token": {
                    "type": "string",
                    "deprecated": True,
                    "description": "Legacy compatibility only. V2 clients must use Authorization Bearer tokens.",
                },
                "id_token": {
                    "type": "string",
                    "deprecated": True,
                    "description": "Legacy compatibility only. V2 clients must use Authorization Bearer tokens.",
                },
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
                "vp_token": {
                    "type": "string",
                    "deprecated": True,
                    "description": "Legacy compatibility only. V2 clients must use Authorization Bearer tokens.",
                },
                "id_token": {
                    "type": "string",
                    "deprecated": True,
                    "description": "Legacy compatibility only. V2 clients must use Authorization Bearer tokens.",
                },
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
                "vp_token": {
                    "type": "string",
                    "deprecated": True,
                    "description": "Legacy compatibility only. V2 clients must use Authorization Bearer tokens.",
                },
                "id_token": {
                    "type": "string",
                    "deprecated": True,
                    "description": "Legacy compatibility only. V2 clients must use Authorization Bearer tokens.",
                },
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
                "vp_token": {
                    "type": "string",
                    "deprecated": True,
                    "description": "Legacy compatibility only. V2 clients must use Authorization Bearer tokens.",
                },
                "id_token": {
                    "type": "string",
                    "deprecated": True,
                    "description": "Legacy compatibility only. V2 clients must use Authorization Bearer tokens.",
                },
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
                "vp_token": {
                    "type": "string",
                    "deprecated": True,
                    "description": "Legacy compatibility only. V2 clients must use Authorization Bearer tokens.",
                },
                "id_token": {
                    "type": "string",
                    "deprecated": True,
                    "description": "Legacy compatibility only. V2 clients must use Authorization Bearer tokens.",
                },
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
                # TODO(auth-cleanup): id_token/vp_token in the DIDComm body are only used in
                # DEMO_MODE for subject tracking. In production the Bearer header is the sole
                # credential carrier. Remove these fields from the schema once the SDK stops
                # sending them in the request body (breaking change — coordinate with SDK release).
            },
            "additionalProperties": True,
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


def _exchange_schemas() -> dict[str, Any]:
    return {
        "DidcommAuthRequest": {
            "type": "object",
            "required": ["body", "meta"],
            "description": (
                "DIDComm-plain auth envelope for tenant-scoped auth endpoints.\n\n"
                "- OAuth/PKCE fields (`client_id`, `code_challenge`, `code`, `code_verifier`, etc.) travel at top-level.\n"
                "- In `2.1 _dcr` backend SDK profile, `client_id` carries the API key value used for binding.\n"
                "- `body` is kept for DIDComm compatibility and can be `{}` for auth requests.\n"
                "- `meta.jws.protected.jwk` carries the controller message-signing public key."
            ),
            "properties": {
                "thid": {"type": "string", "example": "auth-thid-001"},
                "type": {"type": "string", "example": "application/bundle-api+json"},
                "iat": {"type": "integer", "example": 1760000000},
                "exp": {"type": "integer", "example": 1760003600},
                "body": {"type": "object", "additionalProperties": True},
                "attachments": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "meta": {
                    "type": "object",
                    "properties": {
                        "jws": {
                            "type": "object",
                            "properties": {
                                "protected": {
                                    "type": "object",
                                    "properties": {
                                        "alg": {"type": "string", "example": "ES384"},
                                        "kid": {"type": "string", "example": "controller-es384-001"},
                                        "jwk": {"type": "object", "additionalProperties": True},
                                    },
                                    "required": ["jwk"],
                                }
                            },
                        }
                    },
                    "required": ["jws"],
                },
            },
            "additionalProperties": True,
        },
        "AuthAsyncAcceptedResponse": {
            "type": "object",
            "required": ["detail"],
            "properties": {
                "detail": {"type": "string", "example": "Accepted"},
            },
            "description": "Submit-step response metadata is carried in HTTP headers (`Location`, `Retry-After`).",
            "additionalProperties": True,
        },
        "AuthAsyncPollResponse": {
            "type": "object",
            "required": ["thid"],
            "properties": {
                "thid": {"type": "string", "example": "auth-thid-001"},
                "status": {"type": "string", "example": "ok"},
                "action": {"type": "string", "example": "_token"},
                "code": {"type": "string", "example": "c2d3f1aa-1d5c-4600-b9b0-973f2f0f2f4e"},
                "id_token": {"type": "string", "example": "<JWT>"},
                "token_type": {"type": "string", "example": "urn:ietf:params:oauth:token-type:id_token"},
                "expires_in": {"type": "integer", "example": 300},
                "access_token": {"type": "string", "example": "<JWT>"},
                "scope": {"type": "string", "example": "dataconv.upload dataconv.search"},
            },
            "additionalProperties": True,
        },
        "TokenExchangeRequest": {
            "type": "object",
            "description": (
                "RFC 8693 token exchange request used in controller bootstrap (`.../organization/dataspace/auth/_exchange`) and tenant-scoped "
                "auth exchange step (`.../identity/auth/_exchange`)."
            ),
            "properties": {
                "grant_type": {
                    "type": "string",
                    "default": "urn:ietf:params:oauth:grant-type:token-exchange",
                    "example": "urn:ietf:params:oauth:grant-type:token-exchange",
                    "description": "RFC 8693 grant type. Optional — value is ignored; only token-exchange is supported.",
                },
                "subject_token": {
                    "type": "string",
                    "description": "OIDC `id_token` JWT issued by a trusted identity provider.",
                },
                "subject_token_type": {
                    "type": "string",
                    "default": "urn:ietf:params:oauth:token-type:id_token",
                    "example": "urn:ietf:params:oauth:token-type:id_token",
                },
                "scope": {
                    "type": "string",
                    "example": "dataconv.upload dataconv.search",
                    "description": "Space-separated list of requested scopes.",
                },
                "api_key": {
                    "type": "string",
                    "description": "Tenant-issued API key. If present, scope is derived from the key policy.",
                },
                "api_key_profile": {
                    "type": "string",
                    "example": "api-key-exception.v1",
                    "description": (
                        "Optional explicit profile for API-key-only exceptional desktop flow. "
                        "Requires server flag `LOCAL_EXCHANGE_ALLOW_API_KEY_EXCEPTION=true`."
                    ),
                },
                "organization": {
                    "type": "string",
                    "description": "Tenant id — required when `api_key` is provided.",
                },
                "vp_token": {
                    "type": "string",
                    "description": "Optional Verifiable Presentation JWT for VP-token binding.",
                },
            },
            "additionalProperties": False,
        },
        "TokenExchangeResponse": {
            "type": "object",
            "required": ["access_token", "token_type", "expires_in"],
            "properties": {
                "access_token": {"type": "string", "description": "Short-lived Bearer JWT for DataConv endpoints."},
                "token_type": {"type": "string", "enum": ["Bearer"]},
                "expires_in": {"type": "integer", "example": 900, "description": "Seconds until expiry."},
                "scope": {"type": "string", "example": "dataconv.upload dataconv.search"},
                "issued_token_type": {
                    "type": "string",
                    "default": "urn:ietf:params:oauth:token-type:access_token",
                },
            },
            "additionalProperties": True,
        },
    }


def _tenant_api_key_schemas() -> dict[str, Any]:
    return {
        "TenantApiKeyActionResource": {
            "type": "object",
            "required": ["@type"],
            "properties": {
                "@context": {"type": "string", "example": "https://schema.org"},
                "@type": {"type": "string", "example": "UpdateAction"},
                "identifier": {"type": "string", "example": "api-key-uuid-1"},
                "actionStatus": {"type": "string", "example": "active"},
                "target": {"type": "string", "example": "publisher/cds-es/v1/animal-care/vates-a00000001/dataset/*/*/_upload"},
                "scope": {
                    "oneOf": [
                        {"type": "string", "example": "dataconv.upload"},
                        {"type": "array", "items": {"type": "string"}, "example": ["dataconv.upload", "dataconv.read"]},
                    ]
                },
                "agent": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string", "example": "alice@example.com"},
                        "sameAs": {"type": "string", "example": "zMockedSameAsHash"},
                    },
                    "additionalProperties": True,
                },
                "instrument": {"type": "object", "additionalProperties": True, "example": {"permission": [{"action": "update"}]}}},
            "additionalProperties": True,
        },
        "TenantApiKeyActionEntry": {
            "type": "object",
            "required": ["resource"],
            "properties": {
                "resource": {"$ref": "#/components/schemas/TenantApiKeyActionResource"}
            },
            "additionalProperties": False,
        },
        "TenantApiKeyActionRequest": {
            "type": "object",
            "required": ["data"],
            "properties": {
                "data": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/TenantApiKeyActionEntry"},
                }
            },
            "additionalProperties": False,
        },
        "TenantApiKeyResource": {
            "type": "object",
            "required": ["@type", "identifier", "actionStatus"],
            "properties": {
                "@context": {"type": "string", "example": "https://schema.org"},
                "@type": {"type": "string", "example": "Person"},
                "identifier": {"type": "string", "example": "api-key-uuid-1"},
                "actionStatus": {"type": "string", "example": "active"},
                "agent": {
                    "type": "object",
                    "properties": {
                        "sameAs": {"type": "string", "example": "zMockedSameAsHash"},
                    },
                    "additionalProperties": True,
                },
                "target": {"type": "string"},
                "scope": {"type": "array", "items": {"type": "string"}},
                "instrument": {"type": "object", "additionalProperties": True},
                "consentRef": {"type": "string", "example": "urn:consent:api-key-rule:abc123..."},
                "consentModel": {"type": "string", "example": "one-rule-one-consent-one-odrl"},
                "tenantId": {"type": "string", "example": "vates-a00000001"},
                "expiresAt": {"type": "string", "example": "2026-03-23T11:22:33Z"},
                "apiKey": {"type": "string", "example": "dck_abc"},
                "removed": {"type": "boolean", "example": True},
            },
            "additionalProperties": True,
        },
        "TenantApiKeyResponseEntry": {
            "type": "object",
            "required": ["resource"],
            "properties": {
                "resource": {"$ref": "#/components/schemas/TenantApiKeyResource"}
            },
            "additionalProperties": False,
        },
        "TenantApiKeyActionResponse": {
            "type": "object",
            "required": ["data"],
            "properties": {
                "data": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/TenantApiKeyResponseEntry"},
                }
            },
            "additionalProperties": True,
        },
    }
