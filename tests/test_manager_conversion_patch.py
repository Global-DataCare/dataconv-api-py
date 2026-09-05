# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.
# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest
from types import SimpleNamespace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapter_ingestion.runtime.adapters import InMemoryBlobStore, InMemorySearchRepository, InMemoryVaultRepository
from adapter_ingestion.service.managers.dependencies import ApiManagerDependencies
from adapter_ingestion.service.managers.conversion_patch import ConversionPatchManager
from adapter_ingestion.service.settings import ServiceSettings


class TestConversionPatchManager(unittest.TestCase):
    def test_handle_updates_user_selected(self) -> None:
        # This PATCH represents explicit human review: it promotes the same
        # processed Firestore resource into the search repository rather than
        # creating a separately transformed resource.
        vault_repo = InMemoryVaultRepository()
        search_repo = InMemorySearchRepository()
        vault_id = "test__es__onehealth-research__test-tenant-123"
        
        # Insert a Composition that points to an Encounter
        composition = {
            "resourceType": "Composition",
            "id": "comp-1",
            "meta": {
                "claims": {
                    "Composition.relatesto-target": "test-thid-123",
                    "Composition.userSelected": "true",
                    "Composition.subject": "Patient:pat-1",
                    "Composition.section": "tests|sec-1",
                    "Composition.entry": "Encounter:enc-1"
                }
            }
        }
        vault_repo.put(vault_id, [composition], "Composition")

        research_subject = {
            "resourceType": "ResearchSubject",
            "id": "pat-1",
            "meta": {
                "claims": {
                    "ResearchSubject.identifier": "urn:uuid:pat-1",
                    "ResearchSubject.status": "candidate",
                    "ResearchSubject.userSelected": "true",
                }
            },
        }
        vault_repo.put(vault_id, [research_subject], "ResearchSubject")
        
        # Insert the actual target resource
        encounter = {
            "resourceType": "Encounter",
            "id": "enc-1",
            "meta": {
                "claims": {
                    "Encounter.userSelected": "true"
                }
            }
        }
        vault_repo.put(vault_id, [encounter], "Encounter")
        
        # Insert the linkage (it's what tells us that enc-1 is an Encounter)
        link = {
            "id": "enc-1",
            "resourceType": "Encounter"
        }
        vault_repo.put(vault_id, [link], "pat-1_sec-1")
        
        deps = ApiManagerDependencies(
            settings=ServiceSettings(
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
                exchange_oidc_allowed_issuers=(),
                exchange_oidc_allowed_audiences=(),
                exchange_oidc_jwks_cache_ttl_seconds=3600,
                exchange_default_allowed_scopes="dataconv.upload",
                exchange_allow_insecure_assertions=True,
                exchange_allow_api_key=False,
                exchange_api_keys=(),
                exchange_api_key_subject_default="",
                exchange_api_key_org_default="",
                job_result_ttl_seconds=3600,
            ),
            control_plane=SimpleNamespace(),
            blob_store=InMemoryBlobStore(),
            vault_repo=vault_repo,
            search_repo=search_repo,
            config_create_responses={}
        )
        manager = ConversionPatchManager(deps)
        
        body = {
            "type": "https://didcomm.org/plaintext/2.0/message",
            "iss": "did:web:example.org:employee:demo",
            "iat": 1000,
            "exp": 2000,
            "thid": "test-thid-123"
        }
        
        request = SimpleNamespace(headers={})
        res = manager.handle(
            tenant_id="test-tenant-123",
            jurisdiction="es",
            sector="onehealth-research",
            software_id="test-v1.0",
            resource_type="Composition",
            response=SimpleNamespace(),
            request=request,
            body=body
        )
        
        self.assertEqual(res["body"]["status"], "success")
        self.assertEqual(res["body"]["promotedCount"], 3)
        self.assertEqual(res["body"]["issues"]["resourceType"], "OperationOutcome")
        self.assertEqual(res["body"]["issues"]["issue"][0]["severity"], "information")
        self.assertNotIn("publication", res["body"])
        self.assertGreaterEqual(len(res["body"]["data"]), 1)
        self.assertEqual(res["body"]["data"][0]["resource"]["@type"], "dcat:Dataset")
        self.assertEqual(
            res["body"]["data"][0]["resource"]["dcat:distribution"][0]["dcat:accessURL"],
            "https://globaldatacare.es/publisher/cds-es/v1/onehealth-research/test-tenant-123/dataset/Composition/_search",
        )
        
        # Verify changes in Vault
        promoted_comp = vault_repo.get(vault_id, "comp-1", "Composition")
        self.assertEqual(promoted_comp["meta"]["claims"]["Composition.userSelected"], "false")
        
        promoted_enc = vault_repo.get(vault_id, "enc-1", "Encounter")
        self.assertEqual(promoted_enc["meta"]["claims"]["Encounter.userSelected"], "false")
        promoted_research_subject = vault_repo.get(vault_id, "pat-1", "ResearchSubject")
        self.assertEqual(
            promoted_research_subject["meta"]["claims"]["ResearchSubject.userSelected"],
            "false",
        )

        indexed_comp = search_repo.search(
            vault_id=vault_id,
            resource_type="Composition",
            search_params={"relatesto-target": "test-thid-123"},
        )
        indexed_enc = search_repo.search(
            vault_id=vault_id,
            resource_type="Encounter",
            search_params={"userSelected": "false"},
        )
        indexed_research_subject = search_repo.search(
            vault_id=vault_id,
            resource_type="ResearchSubject",
            search_params={"identifier": "urn:uuid:pat-1"},
        )
        self.assertEqual(len(indexed_comp), 1)
        self.assertEqual(indexed_comp[0], promoted_comp)
        self.assertEqual(len(indexed_enc), 1)
        self.assertEqual(indexed_enc[0], promoted_enc)
        self.assertEqual(len(indexed_research_subject), 1)
        self.assertEqual(indexed_research_subject[0], promoted_research_subject)

if __name__ == "__main__":
    unittest.main()
