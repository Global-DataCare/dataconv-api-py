# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class ServiceApiContractRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        env = {
            "NODE_ENV": "test",
            "HOST_INTERNAL_IP": "127.0.0.1",
            "PORT": "8080",
            "DB_PROVIDER": "mem",
            "SEARCH_PROVIDER": "mem",
            "QUEUE_PROVIDER": "mem",
            "STORAGE_PROVIDER": "mem",
        }
        self._env_patcher = patch.dict(os.environ, env, clear=False)
        self._env_patcher.start()
        sys.modules.pop("adapter_ingestion.service.api", None)
        service_api = importlib.import_module("adapter_ingestion.service.api")
        self._service_api = importlib.reload(service_api)
        self.app = self._service_api.create_app()

    def tearDown(self) -> None:
        self._env_patcher.stop()

    def test_exposes_canonical_digital_twin_routes(self) -> None:
        paths = {getattr(route, "path", "") for route in self.app.routes}
        self.assertIn(
            "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software_id}/{resource_type}/_upload",
            paths,
        )
        self.assertIn(
            "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software_id}/{resource_type}/_upload-response",
            paths,
        )
        self.assertIn(
            "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software_id}/{resource_type}/_patch",
            paths,
        )
        self.assertIn(
            "/{tenant_id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software_id}/{resource_type}/_batch",
            paths,
        )
        self.assertIn(
            "/host/cds-{jurisdiction}/v1/{sector}/{tenant_id}/org.hl7.fhir.api/{resource_type}/_search",
            paths,
        )

    def test_openapi_uses_canonical_public_paths(self) -> None:
        schema = self.app.openapi()
        paths = schema.get("paths", {})
        self.assertIn(
            "/host/cds-{jurisdiction}/v1/{sector}/{tenant-id}/{software-id}/config/_create",
            paths,
        )
        self.assertIn(
            "/{tenant-id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software-id}/{resource-type}/_upload",
            paths,
        )
        self.assertIn(
            "/{tenant-id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software-id}/{resource-type}/_batch",
            paths,
        )
        self.assertIn(
            "/host/cds-{jurisdiction}/v1/{sector}/{tenant-id}/org.hl7.fhir.api/{resource-type}/_search",
            paths,
        )

    def test_openapi_prunes_fastapi_internal_validation_schemas(self) -> None:
        schema = self.app.openapi()
        component_schemas = schema.get("components", {}).get("schemas", {})
        self.assertNotIn("HTTPValidationError", component_schemas)
        self.assertNotIn("ValidationError", component_schemas)


if __name__ == "__main__":
    unittest.main()
