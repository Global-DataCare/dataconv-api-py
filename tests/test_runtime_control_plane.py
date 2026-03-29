# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapter_ingestion.runtime import ConfigKey, JobRequest, JobStatus, PreconversionControlPlane
from dataclasses import replace
from adapter_ingestion.runtime.adapters import (
    InMemoryConfigStore,
    InMemoryJobQueue,
    InMemoryJobStore,
)


class RuntimeControlPlaneTests(unittest.TestCase):
    def _iso_utc(self, delta_seconds: int) -> str:
        value = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=delta_seconds)
        return value.isoformat().replace("+00:00", "Z")

    def test_resolve_config_with_facility_and_version_fallback(self) -> None:
        config_store = InMemoryConfigStore()
        control = PreconversionControlPlane(
            config_store=config_store,
            job_store=InMemoryJobStore(),
            job_queue=InMemoryJobQueue(),
        )
        control.upsert_config(
            key=ConfigKey(
                alternate_name="franquicia-x",
                manufacturer="qvet",
                manufacturer_version="2026.01",
                country="es",
                facility_id="",
            ),
            content={"schemaConfig": {"headerRowIndex": 1}},
            updated_by="admin-a",
        )
        control.upsert_config(
            key=ConfigKey(
                alternate_name="franquicia-x",
                manufacturer="qvet",
                manufacturer_version="",
                country="",
                facility_id="",
            ),
            content={"schemaConfig": {"headerRowIndex": 2}},
            updated_by="admin-b",
        )

        # exact version+country wins
        resolved = control.resolve_config(
            ConfigKey(
                alternate_name="franquicia-x",
                manufacturer="qvet",
                manufacturer_version="2026.01",
                country="es",
                facility_id="madrid-01",
            )
        )
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.content["schemaConfig"]["headerRowIndex"], 1)

        # unknown version falls back to default version
        resolved_default = control.resolve_config(
            ConfigKey(
                alternate_name="franquicia-x",
                manufacturer="qvet",
                manufacturer_version="2027.99",
                country="mx",
                facility_id="bogota-01",
            )
        )
        self.assertIsNotNone(resolved_default)
        self.assertEqual(resolved_default.content["schemaConfig"]["headerRowIndex"], 2)

    def test_job_lifecycle_in_memory(self) -> None:
        control = PreconversionControlPlane(
            config_store=InMemoryConfigStore(),
            job_store=InMemoryJobStore(),
            job_queue=InMemoryJobQueue(),
        )
        request = JobRequest(
            alternate_name="franquicia-x",
            manufacturer="wakyma",
            manufacturer_version="2026.01",
            country="es",
            facility_id="valencia-02",
            input_ref="upload://session/file.xlsx",
            requested_by="did:web:org:employee:loader",
        )
        queued = control.submit_job(request)
        self.assertEqual(queued.status, JobStatus.QUEUED)
        by_thid = control.get_job_by_thid(queued.thid)
        self.assertIsNotNone(by_thid)
        self.assertEqual(by_thid.job_id, queued.job_id)

        running = control.claim_next_job(worker_id="worker-a")
        self.assertIsNotNone(running)
        self.assertEqual(running.status, JobStatus.RUNNING)

        done = control.mark_job_succeeded(running.job_id, result_ref="gs://bucket/artifacts/job-1")
        self.assertEqual(done.status, JobStatus.SUCCEEDED)
        self.assertEqual(done.result_ref, "gs://bucket/artifacts/job-1")
        delivered = control.mark_job_delivered(done.job_id)
        self.assertTrue(bool(delivered.delivered_at))
        self.assertTrue(control.delete_job(done.job_id))
        self.assertIsNone(control.get_job(done.job_id))

    def test_cleanup_expired_jobs_scans_all_tenants(self) -> None:
        control = PreconversionControlPlane(
            config_store=InMemoryConfigStore(),
            job_store=InMemoryJobStore(),
            job_queue=InMemoryJobQueue(),
        )

        control.submit_job(
            JobRequest(
                alternate_name="tenant-a",
                manufacturer="qvet",
                input_ref="upload://a1",
            )
        )
        r1 = control.claim_next_job(worker_id="worker")
        self.assertIsNotNone(r1)
        j1 = control.mark_job_succeeded(r1.job_id, result_ref="mem://jobs/a1/summary.json")
        control.job_store.put(replace(j1, finished_at=self._iso_utc(-1000)))

        control.submit_job(
            JobRequest(
                alternate_name="tenant-b",
                manufacturer="wakyma",
                input_ref="upload://b1",
            )
        )
        r2 = control.claim_next_job(worker_id="worker")
        self.assertIsNotNone(r2)
        j2 = control.mark_job_failed(r2.job_id, error="boom")
        control.job_store.put(replace(j2, finished_at=self._iso_utc(-900)))

        control.submit_job(
            JobRequest(
                alternate_name="tenant-c",
                manufacturer="wakyma",
                input_ref="upload://c1",
            )
        )
        r3 = control.claim_next_job(worker_id="worker")
        self.assertIsNotNone(r3)
        j3 = control.mark_job_succeeded(r3.job_id, result_ref="mem://jobs/c1/summary.json")
        control.job_store.put(replace(j3, finished_at=self._iso_utc(-30)))

        report = control.cleanup_expired_jobs(ttl_seconds=300)
        self.assertEqual(report["expired"], 2)
        self.assertEqual(report["deleted"], 2)
        self.assertIsNone(control.get_job(j1.job_id))
        self.assertIsNone(control.get_job(j2.job_id))
        self.assertIsNotNone(control.get_job(j3.job_id))

    def test_cleanup_expired_jobs_dry_run_does_not_delete(self) -> None:
        control = PreconversionControlPlane(
            config_store=InMemoryConfigStore(),
            job_store=InMemoryJobStore(),
            job_queue=InMemoryJobQueue(),
        )
        control.submit_job(
            JobRequest(
                alternate_name="tenant-a",
                manufacturer="qvet",
                input_ref="upload://a1",
            )
        )
        running = control.claim_next_job(worker_id="worker")
        self.assertIsNotNone(running)
        done = control.mark_job_succeeded(running.job_id, result_ref="mem://jobs/a1/summary.json")
        control.job_store.put(replace(done, finished_at=self._iso_utc(-1000)))

        report = control.cleanup_expired_jobs(ttl_seconds=300, dry_run=True)
        self.assertEqual(report["expired"], 1)
        self.assertEqual(report["deleted"], 0)
        self.assertIsNotNone(control.get_job(done.job_id))


if __name__ == "__main__":
    unittest.main()
