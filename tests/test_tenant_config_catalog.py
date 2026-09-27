# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.
# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapter_ingestion.runtime import ConfigKey, PreconversionControlPlane
from adapter_ingestion.runtime.adapters import (
    InMemoryBlobStore,
    InMemoryConfigStore,
    InMemoryJobQueue,
    InMemoryJobStore,
    InMemorySearchRepository,
    InMemoryVaultRepository,
)
from adapter_ingestion.service.managers.dependencies import ApiManagerDependencies
from adapter_ingestion.service.managers.tenant_config_delete import TenantConfigDeleteManager
from adapter_ingestion.service.managers.tenant_config_search import TenantConfigSearchManager
from adapter_ingestion.service.settings import load_settings
from adapter_ingestion.service.api_support import _compose_software_id_token


class TenantConfigCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.control_plane = PreconversionControlPlane(
            InMemoryConfigStore(),
            InMemoryJobStore(),
            InMemoryJobQueue(),
        )
        settings = load_settings()
        self.manager = TenantConfigSearchManager(ApiManagerDependencies(
            settings=settings,
            control_plane=self.control_plane,
            blob_store=InMemoryBlobStore(),
            vault_repo=InMemoryVaultRepository(),
            search_repo=InMemorySearchRepository(),
            config_create_responses={},
        ))
        self.delete_manager = TenantConfigDeleteManager(self.manager._deps)

    def _save(self, *, tenant: str, software: str, version: str, target: str) -> None:
        self.control_plane.upsert_config(
            ConfigKey(
                alternate_name=tenant,
                manufacturer=software,
                manufacturer_version=version,
                sector="animal-research",
                country="CA-BC",
            ),
            {
                "schemaConfig": {
                    "headerRowIndex": 3,
                    "fieldMap": {target: "Diagnostico"},
                },
                "runtimeDefaults": {"dataUse": "secondary"},
            },
            updated_by="did:web:clinic.example:controller",
        )

    @patch("adapter_ingestion.service.managers.tenant_config_search._enforce_auth_context")
    def test_lists_only_the_authorized_tenant_versions_with_editable_public_mappings(self, enforce) -> None:
        self._save(
            tenant="clinic-a",
            software="pinol-vepahi",
            version="v1",
            target="DiagnosticReport.code-text",
        )
        self._save(
            tenant="clinic-a",
            software="pinol-vepahi",
            version="v2",
            target="Condition.code-text",
        )
        self._save(
            tenant="clinic-b",
            software="pinol-vepahi",
            version="v3",
            target="Condition.code-text",
        )

        result = self.manager.search(
            tenant_id="clinic-a",
            jurisdiction="CA-BC",
            sector="animal-research",
            request=SimpleNamespace(headers={"authorization": "Bearer controller-token"}),
            body={"softwareId": "pinol-vepahi", "_count": 20, "_offset": 0},
        )

        self.assertEqual(result["total"], 2)
        self.assertEqual(
            [item["softwareId"] for item in result["data"]],
            [
                _compose_software_id_token("pinol-vepahi", "v1"),
                _compose_software_id_token("pinol-vepahi", "v2"),
            ],
        )
        self.assertEqual(
            result["data"][1]["content"]["mappingConfig"]["fieldMap"],
            {"Condition.code-text": "Diagnostico"},
        )
        self.assertNotIn("schemaConfig", result["data"][1]["content"])
        enforce.assert_called_once_with(
            {},
            self.manager._deps.settings,
            authorization_header="Bearer controller-token",
            require_token=True,
            required_scopes={"dataconv.config.read"},
            enforce_scopes_in_demo=True,
            expected_organization="clinic-a",
        )

    @patch("adapter_ingestion.service.managers.tenant_config_delete._enforce_auth_context")
    def test_deletes_only_the_exact_configuration_owned_by_the_authorized_tenant(self, enforce) -> None:
        self._save(tenant="clinic-a", software="pinol-vepahi", version="v1", target="Condition.code-text")
        self._save(tenant="clinic-b", software="pinol-vepahi", version="v1", target="Condition.code-text")
        owned = next(config for config in self.control_plane.list_configs() if config.key.alternate_name == "clinic-a")

        result = self.delete_manager.delete(
            tenant_id="clinic-a",
            jurisdiction="CA-BC",
            sector="animal-research",
            config_id=owned.object_id,
            request=SimpleNamespace(headers={"authorization": "Bearer controller-token"}),
        )

        self.assertEqual(result, {"deleted": True, "id": owned.object_id})
        self.assertEqual([config.key.alternate_name for config in self.control_plane.list_configs()], ["clinic-b"])
        enforce.assert_called_once_with(
            {},
            self.delete_manager._deps.settings,
            authorization_header="Bearer controller-token",
            require_token=True,
            required_scopes={"dataconv.config.write"},
            enforce_scopes_in_demo=True,
            expected_organization="clinic-a",
        )

    @patch("adapter_ingestion.service.managers.tenant_config_delete._enforce_auth_context")
    def test_hides_a_configuration_owned_by_another_tenant(self, _enforce) -> None:
        self._save(tenant="clinic-b", software="pinol-vepahi", version="v1", target="Condition.code-text")
        foreign = self.control_plane.list_configs()[0]

        with self.assertRaisesRegex(Exception, "Tenant adapter configuration not found") as caught:
            self.delete_manager.delete(
                tenant_id="clinic-a",
                jurisdiction="CA-BC",
                sector="animal-research",
                config_id=foreign.object_id,
                request=SimpleNamespace(headers={"authorization": "Bearer controller-token"}),
            )
        self.assertEqual(getattr(caught.exception, "status_code", None), 404)


if __name__ == "__main__":
    unittest.main()
