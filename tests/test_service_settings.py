# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
import importlib
import os
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class ServiceSettingsTests(unittest.TestCase):
    def _settings_module(self):
        module = importlib.import_module("adapter_ingestion.service.settings")
        return importlib.reload(module)

    def test_profile_defaults_for_dev_like_env(self) -> None:
        settings_module = self._settings_module()
        with patch.object(settings_module, "_load_default_dotenvs", new=lambda: None):
            with patch.dict(
                os.environ,
                {
                    "NODE_ENV": "development",
                    "PRECONV_SECTOR_SCOPE": "animal",
                    "DB_PROVIDER": "firestore",
                    "QUEUE_PROVIDER": "pubsub",
                    "STORAGE_PROVIDER": "gcs",
                },
                clear=True,
            ):
                settings = settings_module.load_settings()

        self.assertEqual(settings.node_env, "development")
        self.assertEqual(settings.search_provider, "mem")
        self.assertEqual(settings.firestore_config_collection, "dev-preconvert-animal-configs")
        self.assertEqual(settings.firestore_job_collection, "dev-preconvert-animal-jobs")
        self.assertEqual(settings.pubsub_topic_id, "dev-preconvert-animal-jobs")
        self.assertEqual(settings.pubsub_subscription_id, "dev-preconvert-animal-jobs-worker")
        self.assertEqual(settings.gcs_prefix, "dev-preconvert-animal")
        self.assertEqual(settings.postgres_search_table, "resource_search_index")

    def test_profile_defaults_for_staging_env(self) -> None:
        settings_module = self._settings_module()
        with patch.object(settings_module, "_load_default_dotenvs", new=lambda: None):
            with patch.dict(
                os.environ,
                {
                    "NODE_ENV": "staging",
                    "PRECONV_SECTOR_SCOPE": "health",
                    "DB_PROVIDER": "firestore",
                    "QUEUE_PROVIDER": "pubsub",
                    "STORAGE_PROVIDER": "gcs",
                },
                clear=True,
            ):
                settings = settings_module.load_settings()

        self.assertEqual(settings.firestore_config_collection, "staging-preconvert-health-configs")
        self.assertEqual(settings.firestore_job_collection, "staging-preconvert-health-jobs")
        self.assertEqual(settings.pubsub_topic_id, "staging-preconvert-health-jobs")
        self.assertEqual(settings.pubsub_subscription_id, "staging-preconvert-health-jobs-worker")
        self.assertEqual(settings.gcs_prefix, "staging-preconvert-health")

    def test_profile_defaults_for_production_env(self) -> None:
        settings_module = self._settings_module()
        with patch.object(settings_module, "_load_default_dotenvs", new=lambda: None):
            with patch.dict(
                os.environ,
                {
                    "NODE_ENV": "production",
                    "PRECONV_SECTOR_SCOPE": "animal",
                    "DB_PROVIDER": "firestore",
                    "QUEUE_PROVIDER": "pubsub",
                    "STORAGE_PROVIDER": "gcs",
                },
                clear=True,
            ):
                settings = settings_module.load_settings()

        self.assertEqual(settings.firestore_config_collection, "prod-preconvert-animal-configs")
        self.assertEqual(settings.firestore_job_collection, "prod-preconvert-animal-jobs")
        self.assertEqual(settings.pubsub_topic_id, "prod-preconvert-animal-jobs")
        self.assertEqual(settings.pubsub_subscription_id, "prod-preconvert-animal-jobs-worker")
        self.assertEqual(settings.gcs_prefix, "prod-preconvert-animal")

    def test_explicit_resource_names_override_environment_profile(self) -> None:
        settings_module = self._settings_module()
        with patch.object(settings_module, "_load_default_dotenvs", new=lambda: None):
            with patch.dict(
                os.environ,
                {
                    "NODE_ENV": "staging",
                    "PRECONV_SECTOR_SCOPE": "animal",
                    "DB_PROVIDER": "firestore",
                    "QUEUE_PROVIDER": "pubsub",
                    "STORAGE_PROVIDER": "gcs",
                    "PRECONV_FIRESTORE_CONFIG_COLLECTION": "custom_configs",
                    "PRECONV_FIRESTORE_JOB_COLLECTION": "custom_jobs",
                    "PRECONV_PUBSUB_TOPIC_ID": "custom-topic",
                    "PRECONV_PUBSUB_SUBSCRIPTION_ID": "custom-subscription",
                    "PRECONV_GCS_PREFIX": "custom-prefix",
                },
                clear=True,
            ):
                settings = settings_module.load_settings()

        self.assertEqual(settings.firestore_config_collection, "custom_configs")
        self.assertEqual(settings.firestore_job_collection, "custom_jobs")
        self.assertEqual(settings.pubsub_topic_id, "custom-topic")
        self.assertEqual(settings.pubsub_subscription_id, "custom-subscription")
        self.assertEqual(settings.gcs_prefix, "custom-prefix")

    def test_sector_defaults_from_vertical_when_scope_not_set(self) -> None:
        settings_module = self._settings_module()
        with patch.object(settings_module, "_load_default_dotenvs", new=lambda: None):
            with patch.dict(
                os.environ,
                {
                    "NODE_ENV": "dev",
                    "ICLAIMS_VERTICAL": "health",
                    "DB_PROVIDER": "firestore",
                    "QUEUE_PROVIDER": "pubsub",
                    "STORAGE_PROVIDER": "gcs",
                },
                clear=True,
            ):
                settings = settings_module.load_settings()

        self.assertEqual(settings.firestore_config_collection, "dev-preconvert-health-configs")
        self.assertEqual(settings.firestore_job_collection, "dev-preconvert-health-jobs")


if __name__ == "__main__":
    unittest.main()
