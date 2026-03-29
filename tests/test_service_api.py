# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
import asyncio
import base64
import inspect
import importlib
import json
import os
import sys
import unittest
from unittest.mock import patch

try:
    from fastapi import HTTPException, Response
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover - optional runtime dependency
    HTTPException = Exception  # type: ignore[assignment]
    Response = None  # type: ignore[assignment]
    TestClient = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class _FakeRequest:
    def __init__(
        self,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
        query_params: dict[str, str] | None = None,
        form_data: dict[str, object] | None = None,
    ) -> None:
        self._body = body
        self.headers = {"authorization": "Bearer demo-token", **(headers or {})}
        self.query_params = query_params or {}
        self._form_data = form_data or {}

    async def body(self) -> bytes:
        return self._body

    async def form(self) -> dict[str, object]:
        return self._form_data


@unittest.skipIf(Response is None, "fastapi runtime dependencies are not installed")
class ServiceApiTests(unittest.TestCase):
    CREATE_PATH = "/host/cds-{jurisdiction}/v1/{sector}/{tenant_id}/{software_id}/config/_create"
    CREATE_RESPONSE_PATH = (
        "/host/cds-{jurisdiction}/v1/{sector}/{tenant_id}/{software_id}/config/_create-response"
    )
    UPLOAD_PATH = (
        "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software_id}/{resource_type}/_upload"
    )
    UPLOAD_RESPONSE_PATH = (
        "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software_id}/{resource_type}/_upload-response"
    )
    _DEFAULT_IAT = 1760000000
    _DEFAULT_EXP = 1760003600

    def setUp(self) -> None:
        env = {
            "NODE_ENV": "test",
            "HOST_INTERNAL_IP": "127.0.0.1",
            "PORT": "8080",
            "DB_PROVIDER": "mem",
            "QUEUE_PROVIDER": "mem",
            "STORAGE_PROVIDER": "mem",
            "PRECONV_LOCAL_DATA_DIR": str(ROOT / "artifacts" / "test-runtime"),
            "PRECONV_DEFAULT_SPECIES_FHIR_FILE": str(
                ROOT / "configs" / "fhir-target-species.template.editable.json"
            ),
            "ICLAIMS_APP_ID": "vet-claims-api",
            "ICLAIMS_VERTICAL": "vet",
            "ICLAIMS_LOCALE": "es",
            "ICLAIMS_CODE_DOMAIN": "none",
            "ICLAIMS_INFERENCE_DOMAIN": "none",
            "DEMO_MODE": "true",
        }
        self._env_patcher = patch.dict(os.environ, env, clear=False)
        self._env_patcher.start()

        sys.modules.pop("adapter_ingestion.service.api", None)
        service_api = importlib.import_module("adapter_ingestion.service.api")
        self._service_api = importlib.reload(service_api)
        self.app = self._service_api.create_app()
        self._thid_software: dict[str, str] = {}

    def tearDown(self) -> None:
        self._env_patcher.stop()

    def _endpoint(self, path: str, method: str = "POST"):
        path = self._normalize_route_path(path)
        for route in self.app.routes:
            if getattr(route, "path", "") != path:
                continue
            methods = getattr(route, "methods", set())
            if method.upper() in methods:
                return self._wrap_endpoint(route.endpoint)
        raise AssertionError(f"Route not found for {method} {path}")

    def _endpoint_from_app(self, app: object, path: str, method: str = "POST"):
        path = self._normalize_route_path(path)
        for route in getattr(app, "routes", []):
            if getattr(route, "path", "") != path:
                continue
            methods = getattr(route, "methods", set())
            if method.upper() in methods:
                return self._wrap_endpoint(route.endpoint)
        raise AssertionError(f"Route not found for {method} {path}")

    def _build_app(self, extra_env: dict[str, str]) -> object:
        with patch.dict(os.environ, extra_env, clear=False):
            sys.modules.pop("adapter_ingestion.service.api", None)
            service_api = importlib.import_module("adapter_ingestion.service.api")
            service_api = importlib.reload(service_api)
            return service_api.create_app()

    def _patch_endpoint_kwargs(self, kwargs: dict[str, object]) -> None:
        if "sector" not in kwargs:
            kwargs["sector"] = "onehealth-research"
        if "source_format" in kwargs and "resource_type" not in kwargs:
            kwargs["resource_type"] = kwargs["source_format"]
        if "tenant_id" in kwargs and "alternate_name" not in kwargs:
            kwargs["alternate_name"] = kwargs["tenant_id"]

        body = kwargs.get("body")
        body_thid = ""
        if isinstance(body, dict):
            body_thid = str(body.get("thid") or "").strip()

        if "manufacturer" not in kwargs:
            if body_thid and body_thid in self._thid_software:
                kwargs["manufacturer"] = self._thid_software[body_thid]

        if "manufacturer" not in kwargs:
            request_obj = kwargs.get("request")
            query_thid = ""
            try:
                query_thid = str(getattr(request_obj, "query_params", {}).get("thid", "") or "").strip()
            except Exception:
                query_thid = ""
            if query_thid and query_thid in self._thid_software:
                kwargs["manufacturer"] = self._thid_software[query_thid]

        if "manufacturer" not in kwargs:
            if isinstance(body, dict):
                data = body.get("data")
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    candidate = data[0].get("softwareId") or data[0].get("software_id") or data[0].get("manufacturer")
                    if isinstance(candidate, str) and candidate.strip():
                        kwargs["manufacturer"] = candidate.strip()
            if "manufacturer" not in kwargs:
                if isinstance(kwargs.get("software_id"), str) and str(kwargs["software_id"]).strip():
                    kwargs["manufacturer"] = str(kwargs["software_id"]).strip()
                else:
                    kwargs["manufacturer"] = "qvet-v1.0"

        if body_thid and isinstance(kwargs.get("manufacturer"), str) and str(kwargs.get("manufacturer") or "").strip():
            self._thid_software[body_thid] = str(kwargs["manufacturer"]).strip()

    def _wrap_endpoint(self, endpoint):
        signature = inspect.signature(endpoint)
        accepted_params = set(signature.parameters.keys())

        def _sanitize_kwargs(kwargs: dict[str, object]) -> dict[str, object]:
            self._patch_endpoint_kwargs(kwargs)
            return {key: value for key, value in kwargs.items() if key in accepted_params}

        if inspect.iscoroutinefunction(endpoint):
            async def _wrapped(*args, **kwargs):
                return await endpoint(*args, **_sanitize_kwargs(kwargs))

            return _wrapped

        def _wrapped(*args, **kwargs):
            return endpoint(*args, **_sanitize_kwargs(kwargs))

        return _wrapped

    @classmethod
    def _normalize_route_path(cls, path: str) -> str:
        mapping = {
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create": cls.CREATE_PATH,
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create-response": cls.CREATE_RESPONSE_PATH,
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload": cls.UPLOAD_PATH,
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload-response": cls.UPLOAD_RESPONSE_PATH,
            "/host/cds-{jurisdiction}/v1/onehealth-research/{tenant_id}/software/config/_create": cls.CREATE_PATH,
            "/host/cds-{jurisdiction}/v1/onehealth-research/{tenant_id}/software/config/_create-response": cls.CREATE_RESPONSE_PATH,
            "/{tenant_id}/cds-{jurisdiction}/v1/onehealth-research/{tenant_scope}/{software_id}/{source_format}/_upload": cls.UPLOAD_PATH,
            "/{tenant_id}/cds-{jurisdiction}/v1/onehealth-research/{tenant_scope}/{software_id}/{source_format}/_upload-response": cls.UPLOAD_RESPONSE_PATH,
        }
        return mapping.get(path, path)

    def _control_plane(self):
        return self.app.state.control_plane

    def _blob_store(self):
        return self.app.state.blob_store

    def _resolve_config(
        self,
        *,
        alternate_name: str,
        manufacturer: str,
        manufacturer_version: str = "",
        country: str = "ES",
        facility_id: str = "",
    ):
        key = self._service_api.ConfigKey(
            alternate_name=alternate_name,
            manufacturer=manufacturer,
            sector="onehealth-research",
            manufacturer_version=manufacturer_version,
            country=country,
            facility_id=facility_id,
        )
        return self._control_plane().resolve_config(key)

    def _jwt(self, claims: dict[str, object]) -> str:
        header = {"alg": "none", "typ": "JWT"}
        header_raw = json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
        claims_raw = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8")
        header_b64 = base64.urlsafe_b64encode(header_raw).decode("ascii").rstrip("=")
        claims_b64 = base64.urlsafe_b64encode(claims_raw).decode("ascii").rstrip("=")
        return f"{header_b64}.{claims_b64}.sig"

    async def _upload_job(
        self,
        payload_override: dict[str, object] | None = None,
        query_params: dict[str, str] | None = None,
        manufacturer: str = "qvet",
        source_format: str = "excel",
    ) -> tuple[str, str, Response]:
        upload_ep = self._endpoint(self.UPLOAD_PATH, method="POST")
        response = Response()
        thid = "job-test-001"
        payload: dict[str, object] = {
            "inputRef": "mem://uploads/input.xlsx",
            "iss": "did:web:test.example:employee:loader",
            "type": "https://didcomm.org/plaintext/2.0/message",
            "thid": thid,
            "jti": thid,
            "iat": self._DEFAULT_IAT,
            "exp": self._DEFAULT_EXP,
        }
        if payload_override:
            payload.update(payload_override)
        await upload_ep(
            tenant_id="tenant-a",
            jurisdiction="es",
            manufacturer=manufacturer,
            source_format=source_format,
            request=_FakeRequest(query_params=query_params),
            response=response,
            file=None,
            body=payload,
        )
        thid_value = str(payload.get("thid") or "")
        job = self._control_plane().get_job_by_thid(thid_value)
        self.assertIsNotNone(job)
        return thid_value, str(job.job_id), response

    def test_create_app_generates_openapi(self) -> None:
        schema = self.app.openapi()
        self.assertIn("openapi", schema)
        self.assertEqual(schema.get("info", {}).get("title"), "Preconversion DIDComm API")
        tag_names = [tag.get("name") for tag in schema.get("tags", []) if isinstance(tag, dict)]
        self.assertIn("1.1 Tenant Configuration Request", tag_names)
        self.assertIn("1.2 Tenant Configuration Response", tag_names)
        self.assertIn("2.1 Conversion Upload Request", tag_names)
        self.assertIn("2.2 Conversion Upload Response", tag_names)
        self.assertIn(
            "/host/cds-{jurisdiction}/v1/{sector}/{tenant-id}/{software-id}/config/_create-response",
            schema.get("paths", {}),
        )
        self.assertIn(
            "/{tenant-id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software-id}/{resource-type}/_upload-response",
            schema.get("paths", {}),
        )
        create_operation = schema["paths"][
            "/host/cds-{jurisdiction}/v1/{sector}/{tenant-id}/{software-id}/config/_create"
        ]["post"]
        create_response_operation = schema["paths"][
            "/host/cds-{jurisdiction}/v1/{sector}/{tenant-id}/{software-id}/config/_create-response"
        ]["post"]
        upload_operation = schema["paths"][
            "/{tenant-id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software-id}/{resource-type}/_upload"
        ]["post"]
        upload_response_operation = schema["paths"][
            "/{tenant-id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software-id}/{resource-type}/_upload-response"
        ]["post"]
        self.assertEqual(create_operation.get("tags"), ["1.1 Tenant Configuration Request"])
        self.assertEqual(create_response_operation.get("tags"), ["1.2 Tenant Configuration Response"])
        self.assertEqual(upload_operation.get("tags"), ["2.1 Conversion Upload Request"])
        self.assertEqual(upload_response_operation.get("tags"), ["2.2 Conversion Upload Response"])
        parameter_names = [p["name"] for p in upload_operation.get("parameters", [])]
        self.assertIn("tenant-id", parameter_names)
        self.assertIn("software-id", parameter_names)
        self.assertNotIn("manufacturerVersion", parameter_names)
        self.assertNotIn("facilityId", parameter_names)
        self.assertNotIn("requestedBy", parameter_names)
        create_response_parameter_names = [p["name"] for p in create_response_operation.get("parameters", [])]
        upload_response_parameter_names = [p["name"] for p in upload_response_operation.get("parameters", [])]
        self.assertIn("thid", create_response_parameter_names)
        self.assertIn("thid", upload_response_parameter_names)

        create_request_schema = (
            create_operation.get("requestBody", {})
            .get("content", {})
            .get("application/didcomm-plain+json", {})
            .get("schema", {})
        )
        self.assertEqual(
            create_request_schema.get("$ref"),
            "#/components/schemas/DidcommNewOrgConfigCreateRequest",
        )
        create_response_request_schema = (
            create_response_operation.get("requestBody", {})
            .get("content", {})
            .get("application/didcomm-plain+json", {})
            .get("schema", {})
        )
        self.assertEqual(
            create_response_request_schema.get("$ref"),
            "#/components/schemas/DidcommNewOrgConfigPollRequest",
        )

        upload_multipart_schema = (
            upload_operation.get("requestBody", {})
            .get("content", {})
            .get("multipart/form-data", {})
            .get("schema", {})
        )
        self.assertEqual(upload_multipart_schema.get("$ref"), "#/components/schemas/DidcommUploadMultipartRequest")

        upload_json_schema = (
            upload_operation.get("requestBody", {})
            .get("content", {})
            .get("application/didcomm-plain+json", {})
            .get("schema", {})
        )
        self.assertEqual(
            upload_json_schema.get("$ref"),
            "#/components/schemas/DidcommUploadDidcommPlaintextRequest",
        )

        upload_response_schema = (
            upload_response_operation.get("requestBody", {})
            .get("content", {})
            .get("application/didcomm-plain+json", {})
            .get("schema", {})
        )
        self.assertEqual(upload_response_schema.get("$ref"), "#/components/schemas/DidcommUploadResponseRequest")
        create_examples = (
            create_operation.get("requestBody", {})
            .get("content", {})
            .get("application/didcomm-plain+json", {})
            .get("examples", {})
        )
        create_example = (
            create_operation.get("requestBody", {})
            .get("content", {})
            .get("application/didcomm-plain+json", {})
            .get("example", {})
        )
        self.assertEqual(create_examples.get("didcommCreateRequest", {}).get("value", {}).get("jti"), "req-auto")
        self.assertEqual(create_example.get("jti"), "req-auto")
        upload_examples = (
            upload_operation.get("requestBody", {})
            .get("content", {})
            .get("application/didcomm-plain+json", {})
            .get("examples", {})
        )
        upload_example = (
            upload_operation.get("requestBody", {})
            .get("content", {})
            .get("application/didcomm-plain+json", {})
            .get("example", {})
        )
        self.assertEqual(upload_examples.get("didcommUploadWithLink", {}).get("value", {}).get("thid"), "thid-auto")
        self.assertEqual(upload_example.get("thid"), "thid-auto")
        self.assertIn(
            "dl=1",
            upload_examples.get("didcommUploadWithLink", {})
            .get("value", {})
            .get("attachments", [{}])[0]
            .get("data", {})
            .get("links", [""])[0],
        )
        self.assertIn("dl=1", upload_example.get("attachments", [{}])[0].get("data", {}).get("links", [""])[0])
        upload_response_example = (
            upload_response_operation.get("requestBody", {})
            .get("content", {})
            .get("application/didcomm-plain+json", {})
            .get("example", {})
        )
        self.assertEqual(upload_response_example.get("thid"), "thid-auto")

        create_component_props = (
            schema.get("components", {})
            .get("schemas", {})
            .get("DidcommNewOrgConfigCreateRequest", {})
            .get("properties", {})
        )
        create_required = (
            schema.get("components", {})
            .get("schemas", {})
            .get("DidcommNewOrgConfigCreateRequest", {})
            .get("required", [])
        )
        create_request_component = (
            schema.get("components", {})
            .get("schemas", {})
            .get("DidcommNewOrgConfigCreateRequest", {})
        )
        create_poll_request_component = (
            schema.get("components", {})
            .get("schemas", {})
            .get("DidcommNewOrgConfigPollRequest", {})
        )
        upload_multipart_component = (
            schema.get("components", {})
            .get("schemas", {})
            .get("DidcommUploadMultipartRequest", {})
        )
        upload_json_component = (
            schema.get("components", {})
            .get("schemas", {})
            .get("DidcommUploadDidcommPlaintextRequest", {})
        )
        attachment_data_component = (
            schema.get("components", {})
            .get("schemas", {})
            .get("DidcommAttachmentData", {})
        )
        upload_response_component = (
            schema.get("components", {})
            .get("schemas", {})
            .get("DidcommUploadResponseRequest", {})
        )
        self.assertIn("iss", create_component_props)
        self.assertIn("type", create_component_props)
        self.assertIn("thid", create_component_props)
        self.assertIn("jti", create_component_props)
        self.assertIn("iat", create_component_props)
        self.assertIn("exp", create_component_props)
        self.assertNotIn("nbf", create_component_props)
        self.assertIn("iss", create_required)
        self.assertIn("thid", create_required)
        self.assertIn("type", create_required)
        self.assertIn("iat", create_required)
        self.assertIn("exp", create_required)
        self.assertIn("thid", create_poll_request_component.get("required", []))
        self.assertIn("thid", upload_multipart_component.get("required", []))
        self.assertIn("thid", upload_json_component.get("required", []))
        self.assertIn("attachments", upload_json_component.get("required", []))
        self.assertIn("body", upload_json_component.get("required", []))
        self.assertIn("properties", upload_json_component)
        self.assertEqual(
            upload_json_component.get("properties", {}).get("attachments", {}).get("maxItems"),
            1,
        )
        self.assertEqual(
            attachment_data_component.get("properties", {}).get("links", {}).get("maxItems"),
            1,
        )
        self.assertIn("thid", upload_response_component.get("required", []))
        self.assertNotIn("anyOf", create_request_component)
        self.assertNotIn("anyOf", create_poll_request_component)
        self.assertNotIn("anyOf", upload_multipart_component)
        self.assertNotIn("anyOf", upload_json_component)
        self.assertNotIn("anyOf", upload_response_component)

        upload_202 = upload_operation.get("responses", {}).get("202", {})
        self.assertIn("headers", upload_202)
        self.assertIn("Location", upload_202.get("headers", {}))
        self.assertIn("Retry-After", upload_202.get("headers", {}))
        create_202 = create_operation.get("responses", {}).get("202", {})
        self.assertIn("headers", create_202)
        self.assertIn("Location", create_202.get("headers", {}))
        self.assertIn("Retry-After", create_202.get("headers", {}))
        self.assertNotIn("content", create_202)
        self.assertIn("?thid=", create_202.get("headers", {}).get("Location", {}).get("description", ""))
        self.assertIn("?thid=", upload_202.get("headers", {}).get("Location", {}).get("description", ""))
        create_400_content = create_operation.get("responses", {}).get("400", {}).get("content", {})
        self.assertIn("application/didcomm-plain+json", create_400_content)
        self.assertEqual(
            create_400_content["application/didcomm-plain+json"]["schema"].get("$ref"),
            "#/components/schemas/DidcommEarlyErrorResponse",
        )
        early_error_schema = (
            schema.get("components", {})
            .get("schemas", {})
            .get("DidcommEarlyErrorResponse", {})
        )
        early_required = early_error_schema.get("required", [])
        self.assertIn("iss", early_required)
        self.assertIn("aud", early_required)
        self.assertIn("thid", early_required)
        self.assertEqual(create_operation.get("security"), [{"BearerAuth": []}])
        self.assertEqual(create_response_operation.get("security"), [{"BearerAuth": []}])
        self.assertEqual(upload_operation.get("security"), [{"BearerAuth": []}])
        self.assertEqual(upload_response_operation.get("security"), [{"BearerAuth": []}])

        security_schemes = (
            schema.get("components", {})
            .get("securitySchemes", {})
        )
        self.assertIn("BearerAuth", security_schemes)
        self.assertEqual(security_schemes["BearerAuth"].get("type"), "http")
        self.assertEqual(security_schemes["BearerAuth"].get("scheme"), "bearer")

        poll_response_props = (
            schema.get("components", {})
            .get("schemas", {})
            .get("DidcommPollResponse", {})
            .get("properties", {})
        )
        self.assertIn("thid", poll_response_props)
        self.assertIn("body", poll_response_props)
        self.assertNotIn("status", poll_response_props)
        self.assertNotIn("outcome", poll_response_props)
        poll_body_props = poll_response_props.get("body", {}).get("properties", {})
        self.assertIn("resourceType", poll_body_props)
        self.assertIn("type", poll_body_props)
        self.assertIn("issues", poll_body_props)
        self.assertIn("data", poll_body_props)
        create_poll_response_props = (
            schema.get("components", {})
            .get("schemas", {})
            .get("DidcommNewOrgConfigPollResponse", {})
            .get("properties", {})
        )
        self.assertIn("thid", create_poll_response_props)
        self.assertIn("type", create_poll_response_props)
        self.assertIn("body", create_poll_response_props)
        body_props = create_poll_response_props.get("body", {}).get("properties", {})
        self.assertIn("resourceType", body_props)
        self.assertIn("type", body_props)
        self.assertIn("data", body_props)
        self.assertIn("thid", create_poll_response_props)
        self.assertNotIn(
            "DidcommNewOrgConfigAcceptedResponse",
            schema.get("components", {}).get("schemas", {}),
        )

        schema_config_props = (
            schema.get("components", {})
            .get("schemas", {})
            .get("SchemaConfig", {})
            .get("properties", {})
        )
        self.assertIn("excludedSectionFamilies", schema_config_props)

        create_entry_props = (
            schema.get("components", {})
            .get("schemas", {})
            .get("DidcommNewOrgConfigEntry", {})
            .get("properties", {})
        )
        self.assertIn("softwareId", create_entry_props)
        self.assertIn("config", create_entry_props)
        self.assertNotIn("manufacturer", create_entry_props)
        self.assertNotIn("schemaConfig", create_entry_props)

        for operation in (create_operation, create_response_operation, upload_operation, upload_response_operation):
            self.assertNotIn("422", operation.get("responses", {}))

    def test_swagger_ui_is_served_from_api_docs(self) -> None:
        self.assertIsNotNone(TestClient)
        client = TestClient(self.app)

        api_docs_response = client.get("/api-docs")
        self.assertEqual(api_docs_response.status_code, 200)
        self.assertIn("text/html", api_docs_response.headers.get("content-type", ""))

        old_docs_response = client.get("/docs")
        self.assertEqual(old_docs_response.status_code, 404)

    def test_upload_accepts_didcomm_attachment_base64(self) -> None:
        upload_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        response = Response()
        payload_bytes = b"xlsx-inline-bytes"

        asyncio.run(
            upload_ep(
                tenant_id="tenant-a",
                jurisdiction="es",
                manufacturer="qvet",
                source_format="excel",
                request=_FakeRequest(),
                response=response,
                file=None,
                body={
                    "iss": "did:web:test.example:employee:loader",
                    "type": "https://didcomm.org/plaintext/2.0/message",
                    "thid": "job-attachment-base64-001",
                    "jti": "job-attachment-base64-001",
                    "iat": self._DEFAULT_IAT,
                    "exp": self._DEFAULT_EXP,
                    "body": {"resourceType": "Bundle", "type": "batch", "data": [], "total": 0},
                    "attachments": [
                        {
                            "id": "source-xlsx",
                            "filename": "exampleQvetES.xlsx",
                            "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            "data": {"base64": base64.b64encode(payload_bytes).decode("ascii")},
                        }
                    ],
                },
            )
        )

        self.assertEqual(response.headers.get("Retry-After"), "5")
        job = self._control_plane().get_job_by_thid("job-attachment-base64-001")
        self.assertIsNotNone(job)
        self.assertEqual(self._blob_store().get_bytes(job.request.input_ref), payload_bytes)

    def test_upload_accepts_didcomm_attachment_dropbox_link(self) -> None:
        upload_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        response = Response()
        requested_urls: list[str] = []

        class _FakeRemoteResponse:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload
                self.headers = {"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}

            def read(self) -> bytes:
                return self._payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

        def _fake_urlopen(request, timeout=30, context=None):
            requested_urls.append(getattr(request, "full_url", str(request)))
            return _FakeRemoteResponse(b"xlsx-from-link")

        with patch("adapter_ingestion.service.api_support.urlopen", new=_fake_urlopen):
            asyncio.run(
                upload_ep(
                    tenant_id="tenant-a",
                    jurisdiction="es",
                    manufacturer="qvet",
                    source_format="excel",
                    request=_FakeRequest(),
                    response=response,
                    file=None,
                    body={
                        "iss": "did:web:test.example:employee:loader",
                        "type": "https://didcomm.org/plaintext/2.0/message",
                        "thid": "job-attachment-link-001",
                        "jti": "job-attachment-link-001",
                        "iat": self._DEFAULT_IAT,
                        "exp": self._DEFAULT_EXP,
                        "body": {"resourceType": "Bundle", "type": "batch", "data": [], "total": 0},
                        "attachments": [
                            {
                                "id": "source-xlsx",
                                "filename": "exampleQvetES.xlsx",
                                "data": {
                                    "links": [
                                        "https://www.dropbox.com/s/example123/exampleQvetES.xlsx?dl=0"
                                    ]
                                },
                            }
                        ],
                    },
                )
            )

        self.assertEqual(response.headers.get("Retry-After"), "5")
        self.assertEqual(len(requested_urls), 1)
        self.assertIn("dl=1", requested_urls[0])
        job = self._control_plane().get_job_by_thid("job-attachment-link-001")
        self.assertIsNotNone(job)
        self.assertEqual(self._blob_store().get_bytes(job.request.input_ref), b"xlsx-from-link")

    def test_http_upload_accepts_didcomm_plaintext_json(self) -> None:
        self.assertIsNotNone(TestClient)
        client = TestClient(self.app)
        requested_urls: list[str] = []

        class _FakeRemoteResponse:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload
                self.headers = {"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}

            def read(self) -> bytes:
                return self._payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

        def _fake_urlopen(request, timeout=30, context=None):
            requested_urls.append(getattr(request, "full_url", str(request)))
            return _FakeRemoteResponse(b"xlsx-from-http-didcomm")

        with patch("adapter_ingestion.service.api_support.urlopen", new=_fake_urlopen):
            response = client.post(
                "/tenant-a/cds-es/v1/onehealth-research/digitaltwin/qvet/excel/_upload",
                headers={
                    "Content-Type": "application/didcomm-plain+json",
                    "Authorization": "Bearer demo-token",
                },
                content=json.dumps(
                    {
                        "iss": "did:web:test.example:employee:loader",
                        "type": "https://didcomm.org/plaintext/2.0/message",
                        "thid": "job-http-didcomm-001",
                        "jti": "job-http-didcomm-001",
                        "iat": self._DEFAULT_IAT,
                        "exp": self._DEFAULT_EXP,
                        "body": {"resourceType": "Bundle", "type": "batch", "data": [], "total": 0},
                        "attachments": [
                            {
                                "id": "source-xlsx",
                                "filename": "exampleQvetES.xlsx",
                                "data": {
                                    "links": [
                                        "https://www.dropbox.com/scl/fi/gkc57co2y9litpm7t81vt/exampleQvetES.xlsx?rlkey=5cnesxdtop8hfdryhrrlmo89w&dl=1"
                                    ]
                                },
                            }
                        ],
                    }
                ),
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.headers.get("Retry-After"), "5")
        self.assertIn("?thid=job-http-didcomm-001", response.headers.get("Location", ""))
        self.assertEqual(len(requested_urls), 1)
        self.assertIn("dl=1", requested_urls[0])
        job = self._control_plane().get_job_by_thid("job-http-didcomm-001")
        self.assertIsNotNone(job)
        self.assertEqual(self._blob_store().get_bytes(job.request.input_ref), b"xlsx-from-http-didcomm")

    def test_upload_rejects_multiple_links_in_one_attachment(self) -> None:
        upload_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                upload_ep(
                    tenant_id="tenant-a",
                    jurisdiction="es",
                    manufacturer="qvet",
                    source_format="excel",
                    request=_FakeRequest(headers={"authorization": ""}),
                    response=Response(),
                    file=None,
                    body={
                        "iss": "did:web:test.example:employee:loader",
                        "type": "https://didcomm.org/plaintext/2.0/message",
                        "thid": "job-multi-link-001",
                        "jti": "job-multi-link-001",
                        "iat": self._DEFAULT_IAT,
                        "exp": self._DEFAULT_EXP,
                        "body": {"resourceType": "Bundle", "type": "batch", "data": [], "total": 0},
                        "attachments": [
                            {
                                "id": "source-xlsx",
                                "filename": "exampleQvetES.xlsx",
                                "data": {
                                    "links": [
                                        "https://www.dropbox.com/s/example123/exampleQvetES.xlsx?dl=1",
                                        "https://www.dropbox.com/s/example456/exampleQvetES-2.xlsx?dl=1",
                                    ]
                                },
                            }
                        ],
                    },
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("exactly one URL", str(ctx.exception.detail))

    def test_upload_rejects_multiple_attachments(self) -> None:
        upload_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                upload_ep(
                    tenant_id="tenant-a",
                    jurisdiction="es",
                    manufacturer="qvet",
                    source_format="excel",
                    request=_FakeRequest(),
                    response=Response(),
                    file=None,
                    body={
                        "iss": "did:web:test.example:employee:loader",
                        "type": "https://didcomm.org/plaintext/2.0/message",
                        "thid": "job-multi-attachment-001",
                        "jti": "job-multi-attachment-001",
                        "iat": self._DEFAULT_IAT,
                        "exp": self._DEFAULT_EXP,
                        "body": {"resourceType": "Bundle", "type": "batch", "data": [], "total": 0},
                        "attachments": [
                            {"id": "source-1", "data": {"base64": base64.b64encode(b"xlsx-1").decode("ascii")}},
                            {"id": "source-2", "data": {"base64": base64.b64encode(b"xlsx-2").decode("ascii")}},
                        ],
                    },
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("one attachment per upload request", str(ctx.exception.detail))

    def test_upload_accepts_csv_source_format(self) -> None:
        upload_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        response = Response()
        asyncio.run(
            upload_ep(
                tenant_id="tenant-a",
                jurisdiction="es",
                manufacturer="qvet",
                source_format="csv",
                request=_FakeRequest(),
                response=response,
                file=None,
                body={
                    "iss": "did:web:test.example:employee:loader",
                    "type": "https://didcomm.org/plaintext/2.0/message",
                    "thid": "job-csv-001",
                    "jti": "job-csv-001",
                    "iat": self._DEFAULT_IAT,
                    "exp": self._DEFAULT_EXP,
                    "inputRef": "mem://uploads/input.csv",
                },
            )
        )
        self.assertIn("Location", response.headers)
        self.assertIn("/csv/_upload-response?thid=job-csv-001", response.headers["Location"])
        job = self._control_plane().get_job_by_thid("job-csv-001")
        self.assertIsNotNone(job)
        self.assertEqual(str(job.request.input_ref), "mem://uploads/input.csv")

    def test_upload_rejects_empty_body_without_input_ref(self) -> None:
        upload_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                upload_ep(
                    tenant_id="tenant-a",
                    jurisdiction="es",
                    manufacturer="qvet",
                    source_format="excel",
                    request=_FakeRequest(body=b""),
                    response=Response(),
                    file=None,
                    body={
                        "iss": "did:web:test.example:employee:loader",
                        "type": "https://didcomm.org/plaintext/2.0/message",
                        "iat": self._DEFAULT_IAT,
                        "exp": self._DEFAULT_EXP,
                        "thid": "job-empty-001",
                    },
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("empty upload payload", str(ctx.exception.detail))

    def test_upload_requires_type(self) -> None:
        upload_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                upload_ep(
                    tenant_id="tenant-a",
                    jurisdiction="es",
                    manufacturer="qvet",
                    source_format="excel",
                    request=_FakeRequest(),
                    response=Response(),
                    file=None,
                    body={
                        "iss": "did:web:test.example:employee:loader",
                        "iat": self._DEFAULT_IAT,
                        "exp": self._DEFAULT_EXP,
                        "inputRef": "mem://uploads/input.xlsx",
                    },
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(str(ctx.exception.detail), "type is required in DIDComm payload")

    def test_upload_requires_iat(self) -> None:
        upload_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                upload_ep(
                    tenant_id="tenant-a",
                    jurisdiction="es",
                    manufacturer="qvet",
                    source_format="excel",
                    request=_FakeRequest(),
                    response=Response(),
                    file=None,
                    body={
                        "iss": "did:web:test.example:employee:loader",
                        "type": "https://didcomm.org/plaintext/2.0/message",
                        "exp": self._DEFAULT_EXP,
                        "inputRef": "mem://uploads/input.xlsx",
                    },
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(str(ctx.exception.detail), "iat is required in DIDComm payload")

    def test_upload_rejects_exp_before_iat(self) -> None:
        upload_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                upload_ep(
                    tenant_id="tenant-a",
                    jurisdiction="es",
                    manufacturer="qvet",
                    source_format="excel",
                    request=_FakeRequest(),
                    response=Response(),
                    file=None,
                    body={
                        "iss": "did:web:test.example:employee:loader",
                        "type": "https://didcomm.org/plaintext/2.0/message",
                        "iat": self._DEFAULT_EXP,
                        "exp": self._DEFAULT_IAT,
                        "inputRef": "mem://uploads/input.xlsx",
                    },
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(str(ctx.exception.detail), "exp must be greater than or equal to iat")

    def test_upload_rejects_non_didweb_iss(self) -> None:
        upload_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                upload_ep(
                    tenant_id="tenant-a",
                    jurisdiction="es",
                    manufacturer="qvet",
                    source_format="excel",
                    request=_FakeRequest(),
                    response=Response(),
                    file=None,
                    body={
                        "iss": "urn:ietf:rfc:7638:thumbprint-public-sig-key-device",
                        "type": "https://didcomm.org/plaintext/2.0/message",
                        "iat": self._DEFAULT_IAT,
                        "exp": self._DEFAULT_EXP,
                        "inputRef": "mem://uploads/input.xlsx",
                    },
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("did:web", str(ctx.exception.detail))

    def test_upload_production_mode_requires_exchange_bearer(self) -> None:
        app = self._build_app({"DEMO_MODE": "false"})
        upload_ep = self._endpoint_from_app(
            app,
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                upload_ep(
                    tenant_id="tenant-a",
                    jurisdiction="es",
                    manufacturer="qvet",
                    source_format="excel",
                    request=_FakeRequest(),
                    response=Response(),
                    file=None,
                    body={
                        "iss": "did:web:test.example:employee:loader",
                        "type": "https://didcomm.org/plaintext/2.0/message",
                        "iat": self._DEFAULT_IAT,
                        "exp": self._DEFAULT_EXP,
                        "thid": "job-auth-001",
                        "inputRef": "mem://uploads/input.xlsx",
                    },
                )
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_upload_demo_mode_accepts_without_exchange_bearer(self) -> None:
        app = self._build_app({"DEMO_MODE": "true"})
        upload_ep = self._endpoint_from_app(
            app,
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        response = Response()
        payload = asyncio.run(
            upload_ep(
                tenant_id="tenant-a",
                jurisdiction="es",
                manufacturer="qvet",
                source_format="excel",
                request=_FakeRequest(),
                response=response,
                file=None,
                body={
                    "iss": "did:web:test.example:employee:loader",
                    "type": "https://didcomm.org/plaintext/2.0/message",
                    "iat": self._DEFAULT_IAT,
                    "exp": self._DEFAULT_EXP,
                    "thid": "job-auth-bearer-001",
                    "inputRef": "mem://uploads/input.xlsx",
                },
            )
        )
        self.assertIsNone(payload)
        self.assertIn("Location", response.headers)
        self.assertEqual(response.headers.get("Retry-After"), "5")

    def test_upload_rejects_unsupported_sector(self) -> None:
        app = self._build_app({"DEMO_MODE": "true", "SUPPORTED_SECTORS": "animal-care"})
        upload_ep = self._endpoint_from_app(
            app,
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                upload_ep(
                    tenant_id="tenant-a",
                    jurisdiction="es",
                    sector="onehealth-research",
                    manufacturer="qvet",
                    source_format="excel",
                    request=_FakeRequest(),
                    response=Response(),
                    file=None,
                    body={
                        "iss": "did:web:test.example:employee:loader",
                        "type": "https://didcomm.org/plaintext/2.0/message",
                        "iat": self._DEFAULT_IAT,
                        "exp": self._DEFAULT_EXP,
                        "thid": "job-sector-001",
                        "inputRef": "mem://uploads/input.xlsx",
                    },
                )
            )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("sector not supported", str(ctx.exception.detail))

    def test_upload_rejects_unsupported_jurisdiction(self) -> None:
        app = self._build_app({"DEMO_MODE": "true", "SUPPORTED_JURISDICTIONS": "ES"})
        upload_ep = self._endpoint_from_app(
            app,
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                upload_ep(
                    tenant_id="tenant-a",
                    jurisdiction="FR",
                    sector="onehealth-research",
                    manufacturer="qvet",
                    source_format="excel",
                    request=_FakeRequest(),
                    response=Response(),
                    file=None,
                    body={
                        "iss": "did:web:test.example:employee:loader",
                        "type": "https://didcomm.org/plaintext/2.0/message",
                        "iat": self._DEFAULT_IAT,
                        "exp": self._DEFAULT_EXP,
                        "thid": "job-jurisdiction-001",
                        "inputRef": "mem://uploads/input.xlsx",
                    },
                )
            )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("jurisdiction not supported", str(ctx.exception.detail))

    def test_upload_accepts_any_sector_and_jurisdiction_with_wildcards(self) -> None:
        app = self._build_app(
            {
                "DEMO_MODE": "true",
                "SUPPORTED_SECTORS": "*",
                "SUPPORTED_JURISDICTIONS": "*",
            }
        )
        upload_ep = self._endpoint_from_app(
            app,
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        response = Response()
        payload = asyncio.run(
            upload_ep(
                tenant_id="tenant-a",
                jurisdiction="FR",
                sector="custom-research-sector",
                manufacturer="qvet",
                source_format="excel",
                request=_FakeRequest(),
                response=response,
                file=None,
                body={
                    "iss": "did:web:test.example:employee:loader",
                    "type": "https://didcomm.org/plaintext/2.0/message",
                    "iat": self._DEFAULT_IAT,
                    "exp": self._DEFAULT_EXP,
                    "thid": "job-scope-any-001",
                    "inputRef": "mem://uploads/input.xlsx",
                },
            )
        )
        self.assertIsNone(payload)
        self.assertIn("Location", response.headers)

    def test_upload_rejects_disabled_subject(self) -> None:
        app = self._build_app(
            {
                "DEMO_MODE": "true",
                "PRECONV_AUTH_DISABLED_SUBJECTS": "did:web:test.example:employee:loader",
            }
        )
        upload_ep = self._endpoint_from_app(
            app,
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                upload_ep(
                    tenant_id="tenant-a",
                    jurisdiction="es",
                    manufacturer="qvet",
                    source_format="excel",
                    request=_FakeRequest(),
                    response=Response(),
                    file=None,
                    body={
                        "iss": "did:web:test.example:employee:loader",
                        "type": "https://didcomm.org/plaintext/2.0/message",
                        "iat": self._DEFAULT_IAT,
                        "exp": self._DEFAULT_EXP,
                        "thid": "job-auth-004",
                        "inputRef": "mem://uploads/input.xlsx",
                    },
                )
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("subject disabled", str(ctx.exception.detail))

    def test_upload_rejects_disabled_device(self) -> None:
        app = self._build_app(
            {
                "DEMO_MODE": "true",
                "PRECONV_AUTH_DISABLED_DEVICES": "device-001",
            }
        )
        upload_ep = self._endpoint_from_app(
            app,
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                upload_ep(
                    tenant_id="tenant-a",
                    jurisdiction="es",
                    manufacturer="qvet",
                    source_format="excel",
                    request=_FakeRequest(),
                    response=Response(),
                    file=None,
                    body={
                        "iss": "did:web:test.example:employee:loader:device:device-001",
                        "type": "https://didcomm.org/plaintext/2.0/message",
                        "iat": self._DEFAULT_IAT,
                        "exp": self._DEFAULT_EXP,
                        "thid": "job-auth-005",
                        "inputRef": "mem://uploads/input.xlsx",
                    },
                )
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("device disabled", str(ctx.exception.detail))

    def test_upload_response_requires_thid(self) -> None:
        poll_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload-response",
            method="POST",
        )
        with self.assertRaises(HTTPException) as ctx:
            poll_ep(
                tenant_id="tenant-a",
                jurisdiction="es",
                manufacturer="qvet",
                source_format="excel",
                response=Response(),
                request=_FakeRequest(),
                body={
                    "iss": "did:web:test.example:employee:loader",
                    "type": "https://didcomm.org/plaintext/2.0/message",
                    "iat": self._DEFAULT_IAT,
                    "exp": self._DEFAULT_EXP,
                },
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(str(ctx.exception.detail), "thid is required in DIDComm payload")

    def test_upload_response_rejects_invalid_source_format(self) -> None:
        poll_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload-response",
            method="POST",
        )
        with self.assertRaises(HTTPException) as ctx:
            poll_ep(
                tenant_id="tenant-a",
                jurisdiction="es",
                manufacturer="qvet",
                source_format="bad-format",
                response=Response(),
                request=_FakeRequest(),
                body={
                    "iss": "did:web:test.example:employee:loader",
                    "type": "https://didcomm.org/plaintext/2.0/message",
                    "iat": self._DEFAULT_IAT,
                    "exp": self._DEFAULT_EXP,
                    "thid": "job-123",
                },
            )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_upload_response_returns_queued_job_with_202(self) -> None:
        thid, _, upload_response = asyncio.run(self._upload_job())
        self.assertIn("Location", upload_response.headers)
        self.assertEqual(upload_response.headers.get("Retry-After"), "5")
        self.assertIn(
            "/onehealth-research/digitaltwin/qvet/excel/_upload-response?thid=job-test-001",
            upload_response.headers["Location"],
        )

        poll_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload-response",
            method="POST",
        )
        response = Response()
        payload = poll_ep(
            tenant_id="tenant-a",
            jurisdiction="es",
            manufacturer="qvet",
            source_format="excel",
            response=response,
            request=_FakeRequest(),
            body={
                "iss": "did:web:test.example:employee:loader",
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "thid": thid,
            },
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.headers.get("Retry-After"), "5")
        self.assertEqual(payload.get("thid"), thid)
        self.assertEqual(payload.get("body", {}).get("type"), "batch-response")
        self.assertEqual(payload.get("body", {}).get("issues", {}).get("resourceType"), "OperationOutcome")
        self.assertEqual(payload.get("body", {}).get("data", [])[0].get("response", {}).get("status"), "202")
        self.assertEqual(payload.get("body", {}).get("data", [])[0].get("response", {}).get("queuePosition"), 1)
        self.assertNotIn("resource", payload.get("body", {}).get("data", [])[0])

    def test_upload_response_accepts_thid_from_query_param(self) -> None:
        _, _, upload_response = asyncio.run(
            self._upload_job(payload_override={"thid": "job-query-poll-001", "jti": "job-query-poll-001"})
        )
        self.assertIn("?thid=job-query-poll-001", upload_response.headers["Location"])

        poll_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload-response",
            method="POST",
        )
        response = Response()
        payload = poll_ep(
            tenant_id="tenant-a",
            jurisdiction="es",
            manufacturer="qvet",
            source_format="excel",
            response=response,
            request=_FakeRequest(query_params={"thid": "job-query-poll-001"}),
            body={
                "iss": "did:web:test.example:employee:loader",
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
            },
        )
        self.assertEqual(payload.get("thid"), "job-query-poll-001")
        self.assertEqual(payload.get("body", {}).get("data", [])[0].get("response", {}).get("status"), "202")

    def test_upload_response_rejects_mismatched_body_and_query_thid(self) -> None:
        asyncio.run(
            self._upload_job(payload_override={"thid": "job-mismatch-001", "jti": "job-mismatch-001"})
        )
        poll_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload-response",
            method="POST",
        )
        with self.assertRaises(HTTPException) as ctx:
            poll_ep(
                tenant_id="tenant-a",
                jurisdiction="es",
                manufacturer="qvet",
                source_format="excel",
                response=Response(),
                request=_FakeRequest(query_params={"thid": "job-mismatch-001"}),
                body={
                    "iss": "did:web:test.example:employee:loader",
                    "thid": "job-mismatch-002",
                    "type": "https://didcomm.org/plaintext/2.0/message",
                    "iat": self._DEFAULT_IAT,
                    "exp": self._DEFAULT_EXP,
                },
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("thid mismatch", str(ctx.exception.detail))

    def test_upload_response_returns_processed_data_when_succeeded(self) -> None:
        thid, job_id, _ = asyncio.run(self._upload_job())
        job = self._control_plane().claim_next_job(worker_id="test-worker")
        self.assertIsNotNone(job)
        summary_ref = self._blob_store().put_bytes(
            path=f"jobs/{job.job_id}/summary.json",
            payload=(
                b'{"recordsTotal":2,"subjectsTotal":2,"documentReferenceEntries":2,'
                b'"encounterEntries":0,"compositionEntries":2,"status":"ok"}'
            ),
            content_type="application/json",
        )
        self._blob_store().put_bytes(
            path=f"jobs/{job.job_id}/composition-message.json",
            payload=(
                b'{"body": {"resourceType": "Bundle", "type": "batch", "data": '
                b'[{"resource": {"resourceType": "Composition"}}], "total": 1}}'
            ),
            content_type="application/json",
        )
        self._control_plane().mark_job_succeeded(job.job_id, result_ref=summary_ref)
        self.assertEqual(job.job_id, job_id)

        poll_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload-response",
            method="POST",
        )
        response = Response()
        payload = poll_ep(
            tenant_id="tenant-a",
            jurisdiction="es",
            manufacturer="qvet",
            source_format="excel",
            response=response,
            request=_FakeRequest(),
            body={
                "iss": "did:web:test.example:employee:loader",
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "thid": thid,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload.get("thid"), thid)
        self.assertIn("body", payload)
        self.assertEqual(payload["body"].get("type"), "batch-response")
        self.assertEqual(payload["body"].get("issues", {}).get("resourceType"), "OperationOutcome")
        diagnostics = payload["body"]["issues"]["issue"][0]["diagnostics"]
        self.assertIn("Se han procesado 2 registros.", diagnostics)
        self.assertIn("Se han generado 2 Subject.", diagnostics)
        self.assertIn("Se han generado 2 DocumentReference.", diagnostics)
        self.assertIn("Se han generado 0 Encounter.", diagnostics)
        self.assertNotIn("Composition", diagnostics)
        self.assertIn("data", payload["body"])
        self.assertEqual(payload["body"]["data"][0]["response"]["status"], "200")
        self.assertEqual(
            payload["body"]["data"][0]["resource"]["resourceType"],
            "Bundle",
        )
        self.assertEqual(
            payload["body"]["data"][0]["resource"]["data"][0]["resource"]["resourceType"],
            "Composition",
        )
        delivered_job = self._control_plane().get_job_by_thid(thid)
        self.assertIsNotNone(delivered_job)
        self.assertTrue(bool(str(getattr(delivered_job, "delivered_at", "")).strip()))

    def test_upload_response_surfaces_subject_id_drop_diagnostics(self) -> None:
        thid, job_id, _ = asyncio.run(self._upload_job())
        job = self._control_plane().claim_next_job(worker_id="test-worker")
        self.assertIsNotNone(job)
        summary_ref = self._blob_store().put_bytes(
            path=f"jobs/{job.job_id}/summary.json",
            payload=(
                b'{"adapterReport":{"rowsRead":5,"recordsAccepted":0,"recordsDroppedNoSubjectId":5,'
                b'"recordsDroppedMissingLoincMapping":0}}'
            ),
            content_type="application/json",
        )
        self._blob_store().put_bytes(
            path=f"jobs/{job.job_id}/composition-message.json",
            payload=b'{"body":{"resourceType":"Bundle","type":"batch","data":[],"total":0}}',
            content_type="application/json",
        )
        self._control_plane().mark_job_succeeded(job.job_id, result_ref=summary_ref)
        self.assertEqual(job.job_id, job_id)

        poll_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload-response",
            method="POST",
        )
        response = Response()
        payload = poll_ep(
            tenant_id="tenant-a",
            jurisdiction="es",
            manufacturer="qvet",
            source_format="excel",
            response=response,
            request=_FakeRequest(),
            body={
                "iss": "did:web:test.example:employee:loader",
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "thid": thid,
            },
        )
        diagnostics = payload["body"]["issues"]["issue"][0]["diagnostics"]
        self.assertIn("Dropped 5 record", diagnostics)
        self.assertIn("schemaConfig.fieldMap.subject_id", diagnostics)
        self.assertIn("5", diagnostics)

    def test_upload_response_rejects_tenant_or_manufacturer_mismatch(self) -> None:
        thid, _, _ = asyncio.run(self._upload_job())
        poll_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload-response",
            method="POST",
        )

        with self.assertRaises(HTTPException) as wrong_tenant:
            poll_ep(
                tenant_id="other-tenant",
                jurisdiction="es",
                manufacturer="qvet",
                source_format="excel",
                response=Response(),
                request=_FakeRequest(),
                body={
                    "iss": "did:web:test.example:employee:loader",
                    "type": "https://didcomm.org/plaintext/2.0/message",
                    "iat": self._DEFAULT_IAT,
                    "exp": self._DEFAULT_EXP,
                    "thid": thid,
                },
            )
        self.assertEqual(wrong_tenant.exception.status_code, 404)

        with self.assertRaises(HTTPException) as wrong_manufacturer:
            poll_ep(
                tenant_id="tenant-a",
                jurisdiction="es",
                manufacturer="wakyma",
                source_format="excel",
                response=Response(),
                request=_FakeRequest(),
                body={
                    "iss": "did:web:test.example:employee:loader",
                    "type": "https://didcomm.org/plaintext/2.0/message",
                    "iat": self._DEFAULT_IAT,
                    "exp": self._DEFAULT_EXP,
                    "thid": thid,
                },
            )
        self.assertEqual(wrong_manufacturer.exception.status_code, 404)

    def test_upload_uses_iss_as_requested_by_for_bootstrap_config(self) -> None:
        issuer = "did:web:clinic.example:employee:loader"
        asyncio.run(self._upload_job(payload_override={"iss": issuer}))
        config = self._resolve_config(
            alternate_name="tenant-a",
            manufacturer="qvet",
            manufacturer_version="",
            country="ES",
            facility_id="",
        )
        self.assertIsNotNone(config)
        self.assertEqual(config.audit.get("updatedBy"), issuer)

    def test_upload_query_requestedby_is_ignored_and_iss_is_used(self) -> None:
        issuer = "did:web:clinic.example:employee:loader"
        asyncio.run(
            self._upload_job(
                payload_override={"iss": issuer},
                query_params={"requestedBy": "did:web:clinic.example:employee:override"},
            )
        )
        config = self._resolve_config(
            alternate_name="tenant-a",
            manufacturer="qvet",
            manufacturer_version="",
            country="ES",
            facility_id="",
        )
        self.assertIsNotNone(config)
        self.assertEqual(config.audit.get("updatedBy"), issuer)

    def test_upload_api_config_extracts_reserved_config_to_embedded_software_id_defaulting_v1(self) -> None:
        csv_bytes = (
            b"API-CONFIG:language=es:software-id=qvet\n"
            b",date,concept,subject_id,section,family,subfamily,especies\n"
            b"EMPRESA,FECHA,CONCEPTO,CHIP,SECCION,FAMILIA,SUBFAMILIA,ESPECIE\n"
            b"Esteveter,2026-03-01,Consulta,123,clinica,consultas,CONSULTAS,CANINA\n"
        )
        input_ref = self._blob_store().put_bytes(
            path="uploads/api-config.csv",
            payload=csv_bytes,
            content_type="text/csv",
        )

        thid, _, response = asyncio.run(
            self._upload_job(
                payload_override={
                    "inputRef": input_ref,
                    "thid": "job-api-config-001",
                    "jti": "job-api-config-001",
                },
                manufacturer="api-config",
                source_format="csv",
            )
        )
        self.assertEqual(thid, "job-api-config-001")
        self.assertIn("/api-config/csv/_upload-response?thid=job-api-config-001", response.headers["Location"])

        config = self._resolve_config(
            alternate_name="tenant-a",
            manufacturer="qvet",
            manufacturer_version="v1",
            country="ES",
            facility_id="",
        )
        self.assertIsNotNone(config)
        self.assertEqual(config.content["schemaConfig"]["headerRowIndex"], 3)
        self.assertEqual(config.content["schemaConfig"]["fieldMap"]["date"], "FECHA")
        self.assertEqual(config.content["schemaConfig"]["fieldMap"]["subject_id"], "CHIP")
        self.assertEqual(config.content["schemaConfig"]["fieldMap"]["species"], "ESPECIE")

    def test_upload_api_config_requires_embedded_rows_when_reserved_config_missing(self) -> None:
        input_ref = self._blob_store().put_bytes(
            path="uploads/api-config-missing.csv",
            payload=b"EMPRESA,FECHA\nEsteveter,2026-03-01\n",
            content_type="text/csv",
        )

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                self._upload_job(
                    payload_override={
                        "inputRef": input_ref,
                        "thid": "job-api-config-missing-001",
                        "jti": "job-api-config-missing-001",
                    },
                    manufacturer="api-config",
                    source_format="csv",
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("embedded API-CONFIG rows", str(ctx.exception.detail))

    def test_create_config_uses_iss_as_updated_by(self) -> None:
        issuer = "did:web:clinic.example:employee:config-admin"
        create_config = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create",
            method="POST",
        )
        create_response = Response()
        result = create_config(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(),
            response=create_response,
            body={
                "iss": issuer,
                "thid": "cfg-create-updated-by-001",
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "data": [
                    {
                        "softwareId": "qvet-v1.0",
                        "config": {"mappingConfig": {"headerRowIndex": 2}},
                    }
                ],
            },
        )
        self.assertIs(result, create_response)
        self.assertIn("Location", create_response.headers)
        self.assertEqual(create_response.headers.get("Retry-After"), "1")
        config = self._resolve_config(
            alternate_name="tenant-a",
            manufacturer="qvet",
            manufacturer_version="v1.0",
            country="ES",
            facility_id="",
        )
        self.assertIsNotNone(config)
        self.assertEqual(config.audit.get("updatedBy"), issuer)
        self.assertEqual(config.content["schemaConfig"]["headerRowIndex"], 2)

    def test_create_config_rejects_reserved_api_config_software_id(self) -> None:
        issuer = "did:web:clinic.example:employee:config-admin"
        create_config = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create",
            method="POST",
        )
        create_response = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create-response",
            method="POST",
        )

        create_http_response = Response()
        create_config(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(),
            response=create_http_response,
            body={
                "iss": issuer,
                "thid": "cfg-create-api-config-reserved-001",
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "data": [
                    {
                        "softwareId": "api-config",
                        "config": {"mappingConfig": {"headerRowIndex": 3}},
                    }
                ],
            },
        )
        self.assertIn("Location", create_http_response.headers)

        poll_payload = create_response(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(),
            body={
                "iss": issuer,
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "thid": "cfg-create-api-config-reserved-001",
            },
        )
        body_data = poll_payload.get("body", {}).get("data", [])
        self.assertEqual(len(body_data), 1)
        self.assertEqual(body_data[0].get("response", {}).get("status"), "400")
        diagnostics = (
            body_data[0].get("response", {}).get("outcome", {})
            .get("issue", [{}])[0]
            .get("diagnostics", "")
        )
        self.assertIn("softwareId api-config is reserved", diagnostics)

    def test_create_config_accepts_softwareid_and_config_wrapper(self) -> None:
        issuer = "did:web:clinic.example:employee:config-admin"
        create_config = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create",
            method="POST",
        )
        create_response = Response()
        result = create_config(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(),
            response=create_response,
            body={
                "iss": issuer,
                "thid": "cfg-create-wrapper-001",
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "data": [
                    {
                        "softwareId": "qvet-v1.2",
                        "config": {
                            "mappingConfig": {"headerRowIndex": 4},
                        },
                    }
                ],
            },
        )
        self.assertIs(result, create_response)
        self.assertIn("Location", create_response.headers)
        self.assertEqual(create_response.headers.get("Retry-After"), "1")

        config = self._resolve_config(
            alternate_name="tenant-a",
            manufacturer="qvet",
            manufacturer_version="v1.2",
            country="ES",
            facility_id="",
        )
        self.assertIsNotNone(config)
        self.assertEqual(config.audit.get("updatedBy"), issuer)
        self.assertEqual(config.content["schemaConfig"]["headerRowIndex"], 4)
        self.assertIn("runtimeDefaults", config.content)
        self.assertIn("speciesFhir", config.content)

    def test_create_response_returns_accepted_payload_by_thid(self) -> None:
        issuer = "did:web:clinic.example:employee:config-admin"
        create_config = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create",
            method="POST",
        )
        create_response = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create-response",
            method="POST",
        )
        create_http_response = Response()
        result = create_config(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(),
            response=create_http_response,
            body={
                "iss": issuer,
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "thid": "cfg-thread-lookup-001",
                "jti": "cfg-thread-lookup-001",
                "data": [
                    {
                        "softwareId": "qvet-v1.5",
                        "config": {
                            "mappingConfig": {"headerRowIndex": 5},
                        },
                    }
                ],
            },
        )
        self.assertIs(result, create_http_response)
        self.assertIn("Location", create_http_response.headers)
        self.assertIn("?thid=cfg-thread-lookup-001", create_http_response.headers["Location"])
        poll_payload = create_response(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(),
            body={
                "iss": issuer,
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "thid": "cfg-thread-lookup-001",
            },
        )
        self.assertEqual(poll_payload.get("thid"), "cfg-thread-lookup-001")
        self.assertEqual(poll_payload.get("iss"), self.app.state.settings.default_issuer_did)
        self.assertEqual(poll_payload.get("aud"), issuer)
        self.assertEqual(poll_payload.get("type"), "https://didcomm.org/plaintext/2.0/message")
        self.assertIsInstance(poll_payload.get("iat"), int)
        self.assertIsInstance(poll_payload.get("exp"), int)
        self.assertGreaterEqual(int(poll_payload.get("exp") or 0), int(poll_payload.get("iat") or 0))
        body_data = poll_payload.get("body", {}).get("data", [])
        self.assertEqual(len(body_data), 1)
        self.assertIn("issues", poll_payload.get("body", {}))
        self.assertEqual(body_data[0].get("type"), "TenantAdapterConfig")
        self.assertEqual(body_data[0].get("response", {}).get("status"), "200")
        resource = body_data[0].get("resource", {})
        self.assertEqual(resource.get("tenantId"), "tenant-a")
        self.assertEqual(resource.get("softwareId"), "qvet-v1.5")
        self.assertEqual(resource.get("content", {}).get("mappingConfig", {}).get("headerRowIndex"), 5)
        self.assertIn("runtimeDefaults", resource.get("content", {}))
        self.assertNotIn("schemaConfig", resource.get("content", {}))
        self.assertIn("audit", resource)
        self.assertIn("createdBy", resource.get("audit", {}))
        self.assertIn("updatedBy", resource.get("audit", {}))
        self.assertNotIn("softwareVersion", resource)

        with self.assertRaises(HTTPException) as second_read:
            create_response(
                alternate_name="tenant-a",
                jurisdiction="ES",
                request=_FakeRequest(),
                body={
                    "iss": issuer,
                    "type": "https://didcomm.org/plaintext/2.0/message",
                    "iat": self._DEFAULT_IAT,
                    "exp": self._DEFAULT_EXP,
                    "thid": "cfg-thread-lookup-001",
                },
            )
        self.assertEqual(second_read.exception.status_code, 404)
        self.assertIn("not found", str(second_read.exception.detail))

    def test_create_response_accepts_thid_from_query_param(self) -> None:
        issuer = "did:web:clinic.example:employee:config-admin"
        create_config = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create",
            method="POST",
        )
        create_response = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create-response",
            method="POST",
        )
        create_http_response = Response()
        create_config(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(),
            response=create_http_response,
            body={
                "iss": issuer,
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "thid": "cfg-query-001",
                "jti": "req-query-001",
                "data": [{"softwareId": "qvet-v1.0"}],
            },
        )
        self.assertIn("?thid=cfg-query-001", create_http_response.headers["Location"])
        poll_payload = create_response(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(query_params={"thid": "cfg-query-001"}),
            body={
                "iss": issuer,
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
            },
        )
        self.assertEqual(poll_payload.get("thid"), "cfg-query-001")

    def test_create_response_rejects_mismatched_body_and_query_thid(self) -> None:
        issuer = "did:web:clinic.example:employee:config-admin"
        create_config = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create",
            method="POST",
        )
        create_response = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create-response",
            method="POST",
        )
        create_config(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(),
            response=Response(),
            body={
                "iss": issuer,
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "thid": "cfg-mismatch-001",
                "jti": "req-mismatch-001",
                "data": [{"softwareId": "qvet-v1.0"}],
            },
        )
        with self.assertRaises(HTTPException) as ctx:
            create_response(
                alternate_name="tenant-a",
                jurisdiction="ES",
                request=_FakeRequest(query_params={"thid": "cfg-mismatch-001"}),
                body={
                    "iss": issuer,
                    "thid": "cfg-mismatch-002",
                    "type": "https://didcomm.org/plaintext/2.0/message",
                    "iat": self._DEFAULT_IAT,
                    "exp": self._DEFAULT_EXP,
                },
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("thid mismatch", str(ctx.exception.detail))

    def test_create_response_requires_existing_thid(self) -> None:
        create_response = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create-response",
            method="POST",
        )
        with self.assertRaises(HTTPException) as ctx:
            create_response(
                alternate_name="tenant-a",
                jurisdiction="ES",
                request=_FakeRequest(),
                body={
                    "iss": "did:web:clinic.example:employee:config-admin",
                    "type": "https://didcomm.org/plaintext/2.0/message",
                    "iat": self._DEFAULT_IAT,
                    "exp": self._DEFAULT_EXP,
                    "thid": "cfg-thread-missing",
                },
            )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("not found", str(ctx.exception.detail))

    def test_create_response_returns_failed_when_create_has_validation_error_with_thid(self) -> None:
        issuer = "did:web:clinic.example:employee:config-admin"
        create_config = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create",
            method="POST",
        )
        create_response = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create-response",
            method="POST",
        )

        create_http_response = Response()
        create_config(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(),
            response=create_http_response,
            body={
                "iss": issuer,
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "thid": "cfg-thread-failed-001",
                "data": [
                    {
                        "manufacturer": "qvet",
                        "softwareId": "qvet-v1.0",
                    }
                ],
            },
        )
        self.assertIn("Location", create_http_response.headers)

        poll_payload = create_response(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(),
            body={
                "iss": issuer,
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "thid": "cfg-thread-failed-001",
            },
        )
        self.assertEqual(poll_payload.get("thid"), "cfg-thread-failed-001")
        self.assertEqual(poll_payload.get("iss"), self.app.state.settings.default_issuer_did)
        self.assertEqual(poll_payload.get("aud"), issuer)
        self.assertEqual(poll_payload.get("type"), "https://didcomm.org/plaintext/2.0/message")
        self.assertIsInstance(poll_payload.get("iat"), int)
        self.assertIsInstance(poll_payload.get("exp"), int)
        body_data = poll_payload.get("body", {}).get("data", [])
        self.assertEqual(len(body_data), 1)
        self.assertEqual(body_data[0].get("response", {}).get("status"), "400")
        diagnostics = (
            body_data[0].get("response", {}).get("outcome", {})
            .get("issue", [{}])[0]
            .get("diagnostics", "")
        )
        self.assertIn("legacy entry fields are not supported", diagnostics)

    def test_create_config_requires_type(self) -> None:
        create_config = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create",
            method="POST",
        )
        create_response = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create-response",
            method="POST",
        )
        create_http_response = Response()
        create_config(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(),
            response=create_http_response,
            body={
                "iss": "did:web:clinic.example:employee:config-admin",
                "thid": "cfg-create-missing-type-001",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "data": [{"softwareId": "qvet-v1.0"}],
            },
        )
        self.assertIn("Location", create_http_response.headers)
        poll_payload = create_response(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(),
            body={
                "iss": "did:web:clinic.example:employee:config-admin",
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "thid": "cfg-create-missing-type-001",
            },
        )
        body_data = poll_payload.get("body", {}).get("data", [])
        self.assertEqual(len(body_data), 1)
        self.assertEqual(body_data[0].get("response", {}).get("status"), "400")
        diagnostics = (
            body_data[0].get("response", {}).get("outcome", {})
            .get("issue", [{}])[0]
            .get("diagnostics", "")
        )
        self.assertIn("type is required in DIDComm payload", diagnostics)

    def test_create_config_requires_thid(self) -> None:
        create_config = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create",
            method="POST",
        )
        with self.assertRaises(HTTPException) as ctx:
            create_config(
                alternate_name="tenant-a",
                jurisdiction="ES",
                request=_FakeRequest(),
                response=Response(),
                body={
                    "iss": "did:web:clinic.example:employee:config-admin",
                    "type": "https://didcomm.org/plaintext/2.0/message",
                    "iat": self._DEFAULT_IAT,
                    "exp": self._DEFAULT_EXP,
                    "data": [{"softwareId": "qvet-v1.0"}],
                },
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(str(ctx.exception.detail), "thid is required in DIDComm payload")

    def test_create_config_accepts_multiple_direct_data_entries(self) -> None:
        issuer = "did:web:clinic.example:employee:batch-admin"
        create_config = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create",
            method="POST",
        )
        create_config(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(),
            response=Response(),
            body={
                "iss": issuer,
                "thid": "cfg-create-multi-001",
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "data": [
                    {
                        "softwareId": "qvet-v1.0",
                        "config": {"mappingConfig": {"headerRowIndex": 2}},
                    },
                    {
                        "softwareId": "wakyma-v2.4",
                        "config": {"mappingConfig": {"headerRowIndex": 3}},
                    },
                ],
            },
        )
        qvet = self._resolve_config(
            alternate_name="tenant-a",
            manufacturer="qvet",
            manufacturer_version="v1.0",
            country="ES",
            facility_id="",
        )
        wakyma = self._resolve_config(
            alternate_name="tenant-a",
            manufacturer="wakyma",
            manufacturer_version="v2.4",
            country="ES",
            facility_id="",
        )
        self.assertIsNotNone(qvet)
        self.assertIsNone(wakyma)
        self.assertEqual(qvet.content["schemaConfig"]["headerRowIndex"], 2)

    def test_create_config_mixed_success_and_failure_entries(self) -> None:
        issuer = "did:web:clinic.example:employee:batch-admin"
        create_config = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create",
            method="POST",
        )
        create_response = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create-response",
            method="POST",
        )
        create_config(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(),
            response=Response(),
            body={
                "iss": issuer,
                "thid": "cfg-create-mixed-001",
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "data": [
                    {
                        "softwareId": "qvet-v1.0",
                        "config": {"mappingConfig": {"headerRowIndex": 2}},
                    },
                    {
                        "manufacturer": "legacy-should-fail",
                        "softwareId": "wakyma-v2.4",
                    },
                ],
            },
        )
        poll_payload = create_response(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(),
            body={
                "iss": issuer,
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "thid": "cfg-create-mixed-001",
            },
        )
        data_entries = poll_payload.get("body", {}).get("data", [])
        self.assertEqual(len(data_entries), 2)
        self.assertIn("issues", poll_payload.get("body", {}))
        statuses = sorted(str(item.get("response", {}).get("status", "")) for item in data_entries)
        self.assertEqual(statuses, ["200", "400"])
        for item in data_entries:
            self.assertEqual(item.get("type"), "TenantAdapterConfig")
            self.assertIsInstance(item.get("resource"), dict)

        qvet = self._resolve_config(
            alternate_name="tenant-a",
            manufacturer="qvet",
            manufacturer_version="v1.0",
            country="ES",
            facility_id="",
        )
        self.assertIsNotNone(qvet)
        self.assertEqual(qvet.content["schemaConfig"]["headerRowIndex"], 2)

    def test_create_config_rejects_legacy_entry_fields(self) -> None:
        create_config = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create",
            method="POST",
        )
        create_response = self._endpoint(
            "/host/cds-{jurisdiction}/v1/animal-care/{alternate_name}/config/didcomm/_create-response",
            method="POST",
        )
        issuer = "did:web:clinic.example:employee:config-admin"
        result = create_config(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(),
            response=Response(),
            body={
                "iss": issuer,
                "thid": "cfg-create-legacy-001",
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "data": [{"manufacturer": "qvet-v1.0", "schemaConfig": {"headerRowIndex": 2}}],
            },
        )
        self.assertIsNotNone(result)
        poll_payload = create_response(
            alternate_name="tenant-a",
            jurisdiction="ES",
            request=_FakeRequest(),
            body={
                "iss": issuer,
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
                "thid": "cfg-create-legacy-001",
            },
        )
        data_entries = poll_payload.get("body", {}).get("data", [])
        self.assertEqual(len(data_entries), 1)
        first = data_entries[0]
        self.assertEqual(first.get("type"), "TenantAdapterConfig")
        self.assertIsInstance(first.get("resource"), dict)
        self.assertEqual(first.get("response", {}).get("status"), "400")
        diagnostics = (
            first.get("response", {})
            .get("outcome", {})
            .get("issue", [{}])[0]
            .get("diagnostics", "")
        )
        self.assertIn("legacy entry fields are not supported", str(diagnostics))

    def test_upload_parses_manufacturer_version_from_path_token(self) -> None:
        issuer = "did:web:clinic.example:employee:loader"
        asyncio.run(
            self._upload_job(
                payload_override={"iss": issuer},
                manufacturer="qvet-v1.0",
            )
        )
        config = self._resolve_config(
            alternate_name="tenant-a",
            manufacturer="qvet",
            manufacturer_version="v1.0",
            country="ES",
            facility_id="",
        )
        self.assertIsNotNone(config)
        self.assertEqual(config.audit.get("updatedBy"), issuer)

    def test_upload_with_multipart_file_uses_form_thid_and_iss(self) -> None:
        from io import BytesIO

        from starlette.datastructures import UploadFile

        upload_ep = self._endpoint(
            "/{tenant_id}/cds-{jurisdiction}/v1/animal-care/conversion/{manufacturer}/{source_format}/_upload",
            method="POST",
        )
        thid = "job-form-001"
        file_obj = UploadFile(file=BytesIO(b"xlsx-bytes"), filename="input.xlsx")
        response = Response()
        payload = asyncio.run(
            upload_ep(
                tenant_id="tenant-a",
                jurisdiction="es",
                manufacturer="qvet-v1.0",
                source_format="excel",
                request=_FakeRequest(
                    form_data={
                        "iss": "did:web:clinic.example:employee:loader",
                        "type": "https://didcomm.org/plaintext/2.0/message",
                        "thid": thid,
                        "iat": str(self._DEFAULT_IAT),
                        "exp": str(self._DEFAULT_EXP),
                    }
                ),
                response=response,
                file=file_obj,
                body=None,
            )
        )
        self.assertIsNone(payload)
        self.assertEqual(response.headers.get("Retry-After"), "5")
        self.assertIn(
            "/onehealth-research/digitaltwin/qvet-v1.0/excel/_upload-response?thid=job-form-001",
            response.headers["Location"],
        )

    def test_http_exception_is_returned_as_bundle_error_envelope(self) -> None:
        self.assertIsNotNone(TestClient)
        client = TestClient(self.app)
        response = client.post(
            "/tenant-a/cds-es/v1/onehealth-research/digitaltwin/qvet/excel/_upload-response",
            json={
                "iss": "did:web:test.example:employee:loader",
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iat": self._DEFAULT_IAT,
                "exp": self._DEFAULT_EXP,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("content-type", "").split(";")[0], "application/didcomm-plain+json")
        body = response.json()
        self.assertEqual(body.get("iss"), self.app.state.settings.default_audience_did)
        self.assertEqual(body.get("aud"), "")
        self.assertEqual(body.get("thid"), "")
        self.assertEqual(body.get("type"), "application/bundle-api+json")
        bundle = body.get("body", {})
        self.assertEqual(bundle.get("resourceType"), "Bundle")
        self.assertEqual(bundle.get("data"), [])
        self.assertEqual(bundle.get("total"), 0)
        issues = bundle.get("issues", {})
        self.assertEqual(issues.get("resourceType"), "OperationOutcome")
        self.assertIsInstance(issues.get("issue"), list)

    def test_request_validation_error_returns_400_bundle_error_envelope(self) -> None:
        self.assertIsNotNone(TestClient)
        client = TestClient(self.app)
        response = client.post(
            "/host/cds-ES/v1/onehealth-research/tenant-a/qvet/config/_create",
            json=["not-an-object"],
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("content-type", "").split(";")[0], "application/didcomm-plain+json")
        body = response.json()
        self.assertEqual(body.get("iss"), self.app.state.settings.default_audience_did)
        self.assertEqual(body.get("aud"), "")
        self.assertEqual(body.get("thid"), "")
        self.assertEqual(body.get("type"), "application/bundle-api+json")
        bundle = body.get("body", {})
        self.assertEqual(bundle.get("resourceType"), "Bundle")
        self.assertEqual(bundle.get("data"), [])
        self.assertEqual(bundle.get("total"), 0)
        issues = bundle.get("issues", {})
        self.assertEqual(issues.get("resourceType"), "OperationOutcome")
        self.assertIsInstance(issues.get("issue"), list)


if __name__ == "__main__":
    unittest.main()
