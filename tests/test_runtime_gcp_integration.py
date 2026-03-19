# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
import os
import sys
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapter_ingestion.runtime import ConfigKey, JobRequest, JobStatus, PreconversionControlPlane
from adapter_ingestion.runtime.adapters import FirestoreConfigStore, FirestoreJobStore, FirestoreVaultRepository, GCSBlobStore, PubSubJobQueue


class GcpRuntimeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.getenv("RUN_GCP_INTEGRATION", "").strip() != "1":
            raise unittest.SkipTest("Set RUN_GCP_INTEGRATION=1 to run GCP adapter integration tests.")

        cls.project_id = str(os.getenv("GCP_PROJECT_ID", "")).strip()
        cls.bucket_name = str(os.getenv("GCS_BUCKET_NAME", "")).strip()
        if not cls.project_id or not cls.bucket_name:
            raise unittest.SkipTest("GCP_PROJECT_ID and GCS_BUCKET_NAME are required for GCP integration tests.")

        try:
            from google.cloud import pubsub_v1
            from google.cloud import storage
        except ImportError as exc:
            raise unittest.SkipTest(f"Missing google-cloud dependencies: {exc}") from exc

        cls._pubsub_v1 = pubsub_v1
        cls._storage = storage
        cls.run_prefix = f"itest-{time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        cls.config_collection = f"{cls.run_prefix}-configs"
        cls.job_collection = f"{cls.run_prefix}-jobs"
        cls.topic_id = f"{cls.run_prefix}-jobs"
        cls.subscription_id = f"{cls.run_prefix}-jobs-worker"
        cls.gcs_prefix = cls.run_prefix

        cls.publisher = pubsub_v1.PublisherClient()
        cls.subscriber = pubsub_v1.SubscriberClient()
        cls.topic_path = cls.publisher.topic_path(cls.project_id, cls.topic_id)
        cls.subscription_path = cls.subscriber.subscription_path(cls.project_id, cls.subscription_id)
        cls.publisher.create_topic(request={"name": cls.topic_path})
        cls.subscriber.create_subscription(
            request={
                "name": cls.subscription_path,
                "topic": cls.topic_path,
                "ack_deadline_seconds": 20,
            }
        )

        cls.storage_client = storage.Client(project=cls.project_id)
        cls.bucket = cls.storage_client.bucket(cls.bucket_name)

        cls.config_store = FirestoreConfigStore(cls.project_id, cls.config_collection)
        cls.job_store = FirestoreJobStore(cls.project_id, cls.job_collection)
        cls.job_queue = PubSubJobQueue(
            project_id=cls.project_id,
            topic_id=cls.topic_id,
            subscription_id=cls.subscription_id,
        )
        cls.vault_repo = FirestoreVaultRepository(cls.project_id)
        cls.blob_store = GCSBlobStore(
            project_id=cls.project_id,
            bucket_name=cls.bucket_name,
            prefix=cls.gcs_prefix,
        )
        cls.control = PreconversionControlPlane(
            config_store=cls.config_store,
            job_store=cls.job_store,
            job_queue=cls.job_queue,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        if not hasattr(cls, "project_id"):
            return

        try:
            from google.api_core.exceptions import NotFound
        except Exception:
            NotFound = Exception

        try:
            for snap in cls.config_store._collection.stream():
                snap.reference.delete()
        except Exception:
            pass

        try:
            for snap in cls.job_store._collection.stream():
                snap.reference.delete()
        except Exception:
            pass

        try:
            for section_id in ("Composition",):
                docs_ref = cls.vault_repo._docs_ref(cls.run_prefix, section_id)  # noqa: SLF001
                for snap in docs_ref.stream():
                    snap.reference.delete()
        except Exception:
            pass

        try:
            for blob in cls.bucket.list_blobs(prefix=f"{cls.gcs_prefix}/"):
                blob.delete()
        except Exception:
            pass

        try:
            cls.subscriber.delete_subscription(request={"subscription": cls.subscription_path})
        except NotFound:
            pass
        except Exception:
            pass

        try:
            cls.publisher.delete_topic(request={"topic": cls.topic_path})
        except NotFound:
            pass
        except Exception:
            pass

    def _claim_with_retry(self, worker_id: str) -> object:
        for _ in range(15):
            running = self.control.claim_next_job(worker_id=worker_id)
            if running is not None:
                return running
            time.sleep(1)
        self.fail("Timed out waiting for Pub/Sub message to become available.")

    def test_firestore_config_roundtrip(self) -> None:
        stored = self.control.upsert_config(
            key=ConfigKey(
                alternate_name="acme",
                manufacturer="qvet",
                manufacturer_version="v1.0",
                country="es",
                facility_id="madrid-01",
            ),
            content={"schemaConfig": {"headerRowIndex": 1}},
            updated_by="fernandolatorre@connecthealth.info",
        )

        resolved = self.control.resolve_config(
            ConfigKey(
                alternate_name="acme",
                manufacturer="qvet",
                manufacturer_version="v1.0",
                country="es",
                facility_id="madrid-01",
            )
        )

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.object_id, stored.object_id)
        self.assertEqual(resolved.revision, 1)
        self.assertEqual(resolved.content["schemaConfig"]["headerRowIndex"], 1)

    def test_firestore_and_pubsub_job_lifecycle_roundtrip(self) -> None:
        queued = self.control.submit_job(
            JobRequest(
                alternate_name="acme",
                manufacturer="qvet",
                manufacturer_version="v1.0",
                country="es",
                facility_id="madrid-01",
                input_ref="gs://api-convert-onehealth/integration/example.xlsx",
                requested_by="did:web:clinic.example:employee:it:loader",
            )
        )
        self.assertEqual(queued.status, JobStatus.QUEUED)

        by_thid = self.control.get_job_by_thid(queued.thid)
        self.assertIsNotNone(by_thid)
        self.assertEqual(by_thid.job_id, queued.job_id)

        running = self._claim_with_retry(worker_id="itest-worker")
        self.assertEqual(running.job_id, queued.job_id)
        self.assertEqual(running.status, JobStatus.RUNNING)

        done = self.control.mark_job_succeeded(
            running.job_id,
            result_ref="gs://api-convert-onehealth/itest/result.json",
        )
        self.assertEqual(done.status, JobStatus.SUCCEEDED)
        self.assertEqual(done.result_ref, "gs://api-convert-onehealth/itest/result.json")

        delivered = self.control.mark_job_delivered(done.job_id)
        self.assertTrue(bool(delivered.delivered_at))
        fetched = self.control.get_job(done.job_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.status, JobStatus.SUCCEEDED)
        self.assertTrue(self.control.delete_job(done.job_id))
        self.assertIsNone(self.control.get_job(done.job_id))

    def test_gcs_blob_roundtrip(self) -> None:
        payload = b'{"resourceType":"Bundle","type":"collection"}'
        ref = self.blob_store.put_bytes(
            path="artifacts/result.json",
            payload=payload,
            content_type="application/json",
        )

        self.assertEqual(
            ref,
            f"gs://{self.bucket_name}/{self.gcs_prefix}/artifacts/result.json",
        )
        self.assertEqual(self.blob_store.get_bytes("artifacts/result.json"), payload)
        self.assertEqual(self.blob_store.get_bytes(ref), payload)

    def test_firestore_vault_query_supports_hyphenated_claim_keys(self) -> None:
        resource = {
            "resourceType": "Composition",
            "id": f"comp-{uuid.uuid4().hex[:8]}",
            "meta": {
                "claims": {
                    "Composition.relatesto-target": "itest-thid-001",
                    "Composition.userSelected": "true",
                }
            },
        }

        self.assertTrue(self.vault_repo.put(self.run_prefix, [resource], "Composition"))

        matched = self.vault_repo.query(
            self.run_prefix,
            {"Composition.relatesto-target": "itest-thid-001"},
            "Composition",
        )

        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["id"], resource["id"])


if __name__ == "__main__":
    unittest.main()
