# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.
# Flow contract: sector routes isolate tenant data by network and jurisdiction while preserving the public tenant identifier.
# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
import importlib
import os
import sys
import unittest
from unittest.mock import patch

try:
    from fastapi import Response
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover
    Response = None  # type: ignore[assignment]
    TestClient = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@unittest.skipIf(Response is None, "fastapi runtime dependencies are not installed")
class ServiceApiSectorRouteTests(unittest.TestCase):
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
        }
        self._env_patcher = patch.dict(os.environ, env, clear=False)
        self._env_patcher.start()
        sys.modules.pop("adapter_ingestion.service.api", None)
        try:
            service_api = importlib.import_module("adapter_ingestion.service.api")
        except RuntimeError as exc:
            self.skipTest(str(exc))
        self._service_api = importlib.reload(service_api)
        self.app = self._service_api.create_app()

    def tearDown(self) -> None:
        self._env_patcher.stop()

    def _route_paths(self) -> set[str]:
        return {getattr(route, "path", "") for route in self.app.routes}

    def test_new_sector_routes_exist(self) -> None:
        paths = self._route_paths()
        self.assertIn("/host/cds-{jurisdiction}/v1/{sector}/{tenant_id}/{software_id}/config/_create", paths)
        self.assertIn("/host/cds-{jurisdiction}/v1/{sector}/{tenant_id}/{software_id}/config/_create-response", paths)
        self.assertIn("/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software_id}/{resource_type}/_upload", paths)
        self.assertIn("/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software_id}/{resource_type}/_upload-response", paths)
        self.assertIn("/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software_id}/{resource_type}/_patch", paths)
        self.assertIn("/host/cds-{jurisdiction}/v1/{sector}/{tenant_id}/org.hl7.fhir.api/{resource_type}/_search", paths)

    def test_openapi_uses_new_sector_paths(self) -> None:
        schema = self.app.openapi()
        paths = schema.get("paths", {})
        self.assertIn("/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/{software-id}/config/_create", paths)
        self.assertIn("/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/dataset/{software-id}/{resource-type}/_upload", paths)
        self.assertIn("/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/dataset/{software-id}/{resource-type}/_patch", paths)
        self.assertIn("/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/dataset/{resource-type}/_search", paths)

        self.assertIn("/host/cds-{jurisdiction}/v1/{sector}/{tenant-id}/{software-id}/config/_create", paths)
        self.assertIn("/{tenant-id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software-id}/{resource-type}/_upload", paths)
        self.assertIn("/{tenant-id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software-id}/{resource-type}/_patch", paths)
        self.assertIn("/host/cds-{jurisdiction}/v1/{sector}/{tenant-id}/org.hl7.fhir.api/{resource-type}/_search", paths)

    def test_research_subject_search_route_accepts_fhir_parameters(self) -> None:
        self.assertIsNotNone(TestClient)
        identifier = "urn:uuid:11111111-1111-4111-8111-111111111111"
        self.app.state.search_repo.upsert(
            vault_id="test__es__onehealth-research__clinic-a",
            resource_type="ResearchSubject",
            resource={
                "resourceType": "ResearchSubject",
                "id": identifier.removeprefix("urn:uuid:"),
                "meta": {
                    "claims": {
                        "ResearchSubject.identifier": identifier,
                        "ResearchSubject.status": "candidate",
                    }
                },
            },
        )

        response = TestClient(self.app).post(
            "/publisher/cds-ES/v1/onehealth-research/clinic-a/dataset/ResearchSubject/_search",
            json={
                "resourceType": "Parameters",
                "parameter": [{"name": "identifier", "valueUri": identifier}],
            },
        )

        self.assertEqual(response.status_code, 200)
        bundle = response.json()
        self.assertEqual(bundle["resourceType"], "Bundle")
        self.assertEqual(bundle["type"], "searchset")
        self.assertEqual(bundle["total"], 1)


if __name__ == "__main__":
    unittest.main()
