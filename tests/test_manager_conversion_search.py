# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapter_ingestion.runtime.adapters import InMemoryBlobStore, InMemorySearchRepository, InMemoryVaultRepository
from adapter_ingestion.service.managers.conversion_search import ConversionSearchManager
from adapter_ingestion.service.managers.dependencies import ApiManagerDependencies
from adapter_ingestion.service.settings import ServiceSettings


class TestConversionSearchManager(unittest.TestCase):
    def _settings(self) -> ServiceSettings:
        return ServiceSettings(
            node_env="test",
            port=8080,
            host="127.0.0.1",
            db_provider="mem",
            search_provider="mem",
            queue_provider="mem",
            storage_provider="mem",
            local_data_dir=str(ROOT / "artifacts" / "test-runtime"),
            gcp_project_id="",
            gcp_region="europe-west1",
            firestore_config_collection="test-configs",
            firestore_job_collection="test-jobs",
            pubsub_topic_id="test-topic",
            pubsub_subscription_id="test-subscription",
            gcs_bucket_name="",
            gcs_prefix="",
            postgres_dsn="",
            postgres_search_table="resource_search_index",
            default_issuer_did="did:web:globaldatacare.es:employee:preconversion",
            default_audience_did="did:web:globaldatacare.es",
            default_subject_did_prefix="did:web:globaldatacare.es",
            default_species_fhir_file=str(ROOT / "configs" / "fhir-target-species.template.editable.json"),
            iclaims_app_id="app",
            iclaims_vertical="vet",
            iclaims_locale="es",
            iclaims_code_domain="none",
            iclaims_inference_domain="none",
            auth_disabled_subjects=(),
            auth_disabled_devices=(),
            demo_mode=True,
            exchange_session_token_secret="dev-session-secret-change-me",
            exchange_session_token_ttl_seconds=900,
            exchange_oidc_issuer="",
            exchange_oidc_audience="",
            exchange_default_allowed_scopes="dataconv.upload",
            exchange_allow_insecure_assertions=True,
            job_result_ttl_seconds=3600,
        )

    def test_search_reads_from_search_repository(self) -> None:
        search_repo = InMemorySearchRepository()
        vault_id = "onehealth-research_VAT-ESB12345678"
        encounter = {
            "resourceType": "Encounter",
            "id": "enc-1",
            "meta": {
                "claims": {
                    "Encounter.userSelected": "false",
                    "Encounter.identifier": "ENC-1",
                    "Encounter.date": "2026-03-01",
                }
            },
        }
        search_repo.upsert(vault_id=vault_id, resource_type="Encounter", resource=encounter)

        deps = ApiManagerDependencies(
            settings=self._settings(),
            control_plane=SimpleNamespace(),
            blob_store=InMemoryBlobStore(),
            vault_repo=InMemoryVaultRepository(),
            search_repo=search_repo,
            config_create_responses={},
        )
        manager = ConversionSearchManager(deps)
        request = SimpleNamespace(headers={}, query_params={"userselected": "false", "date": "ge2026-01-01"})

        result = manager.handle(
            tenant_id="VAT-ESB12345678",
            jurisdiction="es",
            sector="onehealth-research",
            resource_type="Encounter",
            response=SimpleNamespace(),
            request=request,
            body={},
        )

        self.assertEqual(result["resourceType"], "Bundle")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["entry"][0]["resource"]["id"], "enc-1")


if __name__ == "__main__":
    unittest.main()
