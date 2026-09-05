# Flow contract: processing keeps uploaded bytes in blob storage and persists generated resources as human-review drafts, never as searchable approved data.
# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapter_ingestion.runtime import JobRequest, PreconversionControlPlane
from adapter_ingestion.runtime.adapters import (
    InMemoryBlobStore,
    InMemoryConfigStore,
    InMemoryVaultRepository,
    InMemoryJobQueue,
    InMemoryJobStore,
)
from adapter_ingestion.service.job_processor import process_one_job
from adapter_ingestion.service.settings import ServiceSettings


class _FakeAdapter:
    def read_records(self, input_path, context):  # type: ignore[no-untyped-def]
        return []

    def get_last_report(self) -> dict[str, object]:
        return {}


class JobProcessorResearchDraftsTests(unittest.TestCase):
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
            iclaims_app_id="vet-claims-api",
            iclaims_vertical="vet",
            iclaims_locale="es",
            iclaims_code_domain="none",
            iclaims_inference_domain="none",
            auth_disabled_subjects=(),
            auth_disabled_devices=(),
            demo_mode=False,
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
        )

    def test_process_one_job_persists_research_drafts_and_marks_docref_preliminary(self) -> None:
        # Terminology inference may require human correction, so conversion ends
        # in Firestore-equivalent draft storage with userSelected=true. Search
        # indexing belongs only to the later confirmation/promotion flow.
        control_plane = PreconversionControlPlane(
            config_store=InMemoryConfigStore(),
            job_store=InMemoryJobStore(),
            job_queue=InMemoryJobQueue(),
        )
        blob_store = InMemoryBlobStore()
        vault_repo = InMemoryVaultRepository()
        settings = self._settings()

        input_ref = blob_store.put_bytes(
            path="uploads/test.xlsx",
            payload=b"fake-xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        queued = control_plane.submit_job(
            JobRequest(
                alternate_name="ESB12345678",
                manufacturer="qvet",
                manufacturer_version="v1.0",
                country="ES",
                input_ref=input_ref,
                requested_by="did:web:clinic.example:employee:loader",
                mode="demo-ephemeral",
                thid="job-research-001",
            )
        )

        fake_result = SimpleNamespace(
            composition_message={
                "jti": "msg-1",
                "thid": "job-research-001",
                "type": "https://didcomm.org/plaintext/2.0/message",
                "iss": settings.default_issuer_did,
                "aud": settings.default_audience_did,
                "iat": 1760000000,
                "exp": 1760000300,
                "body": {
                    "resourceType": "Bundle",
                    "type": "batch",
                    "data": [
                        {
                            "resource": {
                                "resourceType": "Subject",
                                "id": "subject-1",
                                "meta": {
                                    "claims": {
                                        "Subject.id": "HISTORIA-001",
                                    }
                                },
                                "contained": [
                                    {
                                        "resourceType": "Composition",
                                        "id": "composition-1",
                                        "meta": {
                                            "claims": {
                                                "Composition.identifier": "composition-1",
                                            }
                                        },
                                    },
                                    {
                                        "resourceType": "DocumentReference",
                                        "id": "docref-1",
                                        "meta": {
                                            "claims": {
                                                "DocumentReference.identifier": "docref-1",
                                                "DocumentReference.subject": "HISTORIA-001",
                                            }
                                        },
                                    },
                                    {
                                        "resourceType": "Encounter",
                                        "id": "enc-1",
                                        "meta": {
                                            "claims": {
                                                "Encounter.identifier": "enc-1",
                                            }
                                        },
                                    },
                                ],
                            }
                        }
                    ],
                    "total": 1,
                },
            },
            summary={"recordsTotal": 1, "subjectsTotal": 1},
        )

        with patch("adapter_ingestion.service.job_processor.get_adapter", return_value=_FakeAdapter()):
            with patch("adapter_ingestion.service.job_processor.run_pipeline", return_value=fake_result):
                processed_job_id = process_one_job(
                    control_plane=control_plane,
                    blob_store=blob_store,
                    vault_repo=vault_repo,
                    settings=settings,
                    worker_id="worker-test",
                )

        self.assertEqual(processed_job_id, queued.job_id)
        stored_job = control_plane.get_job(queued.job_id)
        self.assertIsNotNone(stored_job)
        self.assertEqual(stored_job.status, "succeeded")

        vault_id = "test__es__onehealth-research__esb12345678"
        vault_data = vault_repo._collections.get(vault_id, {})
        
        resource_types = sorted(list(k for k in vault_data.keys() if "_" not in k))
        self.assertEqual(resource_types, ["Composition", "DocumentReference", "Encounter", "Subject"])
        
        subject = vault_repo.get(vault_id, "subject-1", "Subject")
        self.assertEqual(subject["meta"]["claims"]["Subject.userSelected"], "true")
        
        docref = vault_repo.get(vault_id, "docref-1", "DocumentReference")
        self.assertEqual(docref["meta"]["claims"]["DocumentReference.userSelected"], "true")
        self.assertEqual(docref["docStatus"], "preliminary")
        self.assertEqual(docref["meta"]["claims"]["DocumentReference.docStatus"], "preliminary")

        comp = vault_repo.get(vault_id, "composition-1", "Composition")
        self.assertEqual(comp["meta"]["claims"]["Composition.relatesto-target"], "job-research-001")
        self.assertEqual(comp["meta"]["claims"]["Composition.relatesto-type"], "part-of")

        summary_payload = json.loads(blob_store.get_bytes(f"jobs/{queued.job_id}/summary.json").decode("utf-8"))
        self.assertEqual(summary_payload.get("researchDraftsPersisted"), 4)
        self.assertEqual(summary_payload.get("vaultId"), vault_id)
        self.assertEqual(summary_payload.get("softwareId"), "qvet-v1.0")

        composition_payload = json.loads(
            blob_store.get_bytes(f"jobs/{queued.job_id}/composition-message.json").decode("utf-8")
        )
        subject = composition_payload["body"]["data"][0]["resource"]
        self.assertEqual(subject["meta"]["claims"]["Subject.userSelected"], "true")
        document = next(item for item in subject["contained"] if item["resourceType"] == "DocumentReference")
        self.assertEqual(document["meta"]["claims"]["DocumentReference.userSelected"], "true")
        self.assertEqual(document["docStatus"], "preliminary")


if __name__ == "__main__":
    unittest.main()
