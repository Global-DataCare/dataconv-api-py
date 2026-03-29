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

from adapter_ingestion.service.job_processor import (
    PERSONAL_ID_ALIAS_SECTION,
    _build_context,
    _language_from_country,
    _species_catalog_from_file,
    _species_local_map_from_config,
)
from adapter_ingestion.service.settings import ServiceSettings
from adapter_ingestion.runtime.adapters import InMemoryVaultRepository


class JobProcessorSpeciesMapTests(unittest.TestCase):
    def _settings(self) -> ServiceSettings:
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
            default_species_fhir_file="./configs/fhir-target-species.template.editable.json",
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
            exchange_default_allowed_scopes="dataconv.upload",
            exchange_allow_insecure_assertions=True,
            job_result_ttl_seconds=3600,
        )

    def test_species_local_map_from_config_flat(self) -> None:
        mapping = _species_local_map_from_config(
            {
                "speciesLocalToFhirCode": {
                    "Perró": "100000108988",
                    "Gato": "100000109056",
                }
            }
        )
        self.assertEqual(mapping.get("Perró"), "100000108988")
        self.assertEqual(mapping.get("PERRÓ"), "100000108988")
        self.assertEqual(mapping.get("perro"), "100000108988")
        self.assertEqual(mapping.get("Gato"), "100000109056")
        self.assertEqual(mapping.get("gato"), "100000109056")

    def test_species_local_map_from_config_returns_empty_when_missing(self) -> None:
        mapping = _species_local_map_from_config(
            {
                "speciesLocalMap": {
                    "speciesLocalToFhirCode": {
                        "CANINA": "100000108988",
                    }
                },
            }
        )
        self.assertEqual(mapping, {})

    def test_build_context_uses_species_fhir_key(self) -> None:
        context = _build_context(
            settings=self._settings(),
            request_alternate_name="acme",
            request_country="es",
            request_manufacturer="qvet",
            config_payload={
                "speciesFhir": {
                    "system": "http://hl7.org/fhir/target-species",
                    "codes": {
                        "100000108988": "Dogs",
                    },
                }
            },
        )
        self.assertEqual(context.fhir_species_system, "http://hl7.org/fhir/target-species")
        self.assertEqual(context.fhir_species_catalog.get("100000108988"), "Dogs")

    def test_build_context_fallback_species_catalog_for_backward_compat(self) -> None:
        context = _build_context(
            settings=self._settings(),
            request_alternate_name="acme",
            request_country="es",
            request_manufacturer="qvet",
            config_payload={
                "speciesCatalog": {
                    "system": "http://hl7.org/fhir/target-species",
                    "codes": {
                        "100000109056": "Cats",
                    },
                }
            },
        )
        self.assertEqual(context.fhir_species_catalog.get("100000109056"), "Cats")

    def test_species_catalog_from_file_loads_static_catalog(self) -> None:
        payload = {
            "system": "http://hl7.org/fhir/target-species",
            "codes": {
                "100000108988": "Dogs",
            },
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(payload, tmp, ensure_ascii=False)
            path = tmp.name
        try:
            system, catalog = _species_catalog_from_file(path)
            self.assertEqual(system, "http://hl7.org/fhir/target-species")
            self.assertEqual(catalog.get("100000108988"), "Dogs")
        finally:
            path_obj = Path(path)
            if path_obj.exists():
                path_obj.unlink()

    def test_language_from_country_defaults(self) -> None:
        self.assertEqual(_language_from_country("es"), "es-ES")
        self.assertEqual(_language_from_country("US"), "en-US")
        self.assertEqual(_language_from_country("es-AR"), "es-AR")

    def test_build_context_uses_country_language_when_runtime_language_missing(self) -> None:
        context = _build_context(
            settings=self._settings(),
            request_alternate_name="acme",
            request_country="es",
            request_manufacturer="qvet",
            config_payload={},
        )
        self.assertEqual(context.language, "es-ES")

    def test_build_context_runtime_language_overrides_country(self) -> None:
        context = _build_context(
            settings=self._settings(),
            request_alternate_name="acme",
            request_country="es",
            request_manufacturer="qvet",
            config_payload={
                "runtimeDefaults": {
                    "language": "ca-ES",
                }
            },
        )
        self.assertEqual(context.language, "ca-ES")

    def test_build_context_personal_id_resolver_persists_uuid_by_hash(self) -> None:
        vault_repo = InMemoryVaultRepository()
        context = _build_context(
            settings=self._settings(),
            request_alternate_name="acme",
            request_country="es",
            request_manufacturer="qvet",
            config_payload={},
            vault_repo=vault_repo,
            settings_target_sector="onehealth-research",
        )

        first = context.personal_id_resolver("12345678A")
        second = context.personal_id_resolver("12345678A")

        self.assertTrue(first)
        self.assertEqual(first, second)
        vault_id = "onehealth-research_acme"
        alias_bucket = vault_repo._collections.get(vault_id, {}).get(PERSONAL_ID_ALIAS_SECTION, {})
        self.assertEqual(len(alias_bucket), 1)
        stored = next(iter(alias_bucket.values()))
        self.assertEqual(stored.get("uuid"), first)

    def test_build_context_personal_id_resolver_returns_empty_for_blank_input(self) -> None:
        vault_repo = InMemoryVaultRepository()
        context = _build_context(
            settings=self._settings(),
            request_alternate_name="acme",
            request_country="es",
            request_manufacturer="qvet",
            config_payload={},
            vault_repo=vault_repo,
            settings_target_sector="onehealth-research",
        )

        self.assertEqual(context.personal_id_resolver(""), "")
        vault_id = "onehealth-research_acme"
        alias_bucket = vault_repo._collections.get(vault_id, {}).get(PERSONAL_ID_ALIAS_SECTION, {})
        self.assertEqual(alias_bucket, {})


if __name__ == "__main__":
    unittest.main()
