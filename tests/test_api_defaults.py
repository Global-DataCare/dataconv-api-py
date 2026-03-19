# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapter_ingestion.service.defaults import default_tenant_config_payload
from adapter_ingestion.service.settings import ServiceSettings


class ApiDefaultsTests(unittest.TestCase):
    def _settings_with_species_file(self, species_file: str) -> ServiceSettings:
        return ServiceSettings(
            node_env="test",
            port=8080,
            host="127.0.0.1",
            db_provider="mem",
            search_provider="mem",
            queue_provider="mem",
            storage_provider="mem",
            local_data_dir="./runtime-data",
            gcp_project_id="",
            gcp_region="europe-west1",
            firestore_config_collection="preconv_configs",
            firestore_job_collection="preconv_jobs",
            pubsub_topic_id="preconv-jobs",
            pubsub_subscription_id="preconv-jobs-worker",
            gcs_bucket_name="",
            gcs_prefix="preconversion",
            postgres_dsn="",
            postgres_search_table="resource_search_index",
            default_issuer_did="did:web:default.issuer",
            default_audience_did="did:web:default.audience",
            default_subject_did_prefix="did:web:default.subject",
            default_species_fhir_file=species_file,
            iclaims_app_id="vet-claims-api",
            iclaims_vertical="vet",
            iclaims_locale="es",
            iclaims_code_domain="none",
            iclaims_inference_domain="none",
            auth_mode="parse-only",
            auth_disabled_subjects=(),
            auth_disabled_devices=(),
            job_result_ttl_seconds=3600,
        )

    def test_default_tenant_config_payload_uses_standard_field_map(self) -> None:
        species_payload = {
            "system": "http://hl7.org/fhir/target-species",
            "codes": {"100000108988": "Dogs"},
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(species_payload, tmp, ensure_ascii=False)
            species_file = tmp.name
        try:
            payload = default_tenant_config_payload(self._settings_with_species_file(species_file))
        finally:
            path_obj = Path(species_file)
            if path_obj.exists():
                path_obj.unlink()

        self.assertEqual(
            payload["schemaConfig"]["fieldMap"],
            {
                "section": "SECTION",
                "family": "FAMILY",
                "subfamily": "SUBFAMILY",
                "concept": "CONCEPT",
                "subjectId": "SUBJECT_ID",
                "owner": "OWNER",
                "ownerId": "OWNER_ID",
                "species": "SPECIES",
                "breed": "BREED",
                "genderStatus": "GENDER_STATUS",
                "date": "DATE",
                "time": "TIME",
            },
        )
        self.assertEqual(payload["speciesFhir"]["codes"].get("100000108988"), "Dogs")
        self.assertEqual(payload["speciesLocalToFhirCode"], {})
        self.assertEqual(payload["schemaConfig"]["encounterClassBySectionFamily"], {})
        self.assertEqual(payload["schemaConfig"]["encounterServiceTypeBySectionFamily"], {})
        self.assertNotIn("patientRules", payload["schemaConfig"])
        self.assertEqual(payload["runtimeDefaults"]["dataUse"], "secondary")


if __name__ == "__main__":
    unittest.main()
