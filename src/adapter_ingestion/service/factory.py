# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from ..runtime import BlobStore, ConfigStore, ISearchRepository, IVaultRepository, JobQueue, JobStore, PreconversionControlPlane
from ..runtime.adapters import (
    FirestoreConfigStore,
    FirestoreJobStore,
    FirestoreVaultRepository,
    GCSBlobStore,
    InMemoryBlobStore,
    InMemoryConfigStore,
    InMemorySearchRepository,
    InMemoryVaultRepository,
    InMemoryJobQueue,
    InMemoryJobStore,
    PostgresSearchRepository,
    PubSubJobQueue,
)
from .settings import ServiceSettings


def build_config_store(settings: ServiceSettings) -> ConfigStore:
    provider = settings.db_provider
    if provider == "firestore":
        return FirestoreConfigStore(
            project_id=settings.gcp_project_id,
            collection=settings.firestore_config_collection,
        )
    if provider == "fs":
        provider = "mem"
    if provider == "mem":
        return InMemoryConfigStore()
    raise ValueError(f"unsupported DB_PROVIDER for config store: {provider}")


def build_job_store(settings: ServiceSettings) -> JobStore:
    provider = settings.db_provider
    if provider == "firestore":
        return FirestoreJobStore(
            project_id=settings.gcp_project_id,
            collection=settings.firestore_job_collection,
        )
    if provider == "fs":
        provider = "mem"
    if provider == "mem":
        return InMemoryJobStore()
    raise ValueError(f"unsupported DB_PROVIDER for jobs: {provider}")


def build_vault_repository(settings: ServiceSettings) -> IVaultRepository:
    provider = settings.db_provider
    if provider == "firestore":
        return FirestoreVaultRepository(
            project_id=settings.gcp_project_id,
        )
    if provider == "fs":
        provider = "mem"
    if provider == "mem":
        return InMemoryVaultRepository()
    raise ValueError(f"unsupported DB_PROVIDER for vaults: {provider}")


def build_search_repository(settings: ServiceSettings) -> ISearchRepository:
    provider = settings.search_provider
    if provider == "fs":
        provider = "mem"
    if provider == "mem":
        return InMemorySearchRepository()
    if provider == "postgresql":
        if not settings.postgres_dsn:
            raise ValueError("POSTGRES_DSN is required when SEARCH_PROVIDER=postgresql")
        return PostgresSearchRepository(
            dsn=settings.postgres_dsn,
            table_name=settings.postgres_search_table,
        )
    raise ValueError(f"unsupported SEARCH_PROVIDER: {provider}")


def build_job_queue(settings: ServiceSettings) -> JobQueue:
    provider = settings.queue_provider
    if provider == "pubsub":
        return PubSubJobQueue(
            project_id=settings.gcp_project_id,
            topic_id=settings.pubsub_topic_id,
            subscription_id=settings.pubsub_subscription_id,
        )
    if provider == "fs":
        provider = "mem"
    if provider == "mem":
        return InMemoryJobQueue()
    if provider == "cloudtasks":
        raise ValueError(
            "QUEUE_PROVIDER=cloudtasks is push-model and not supported by pull worker. "
            "Use QUEUE_PROVIDER=pubsub for worker polling in Kubernetes."
        )
    raise ValueError(f"unsupported QUEUE_PROVIDER: {provider}")


def build_blob_store(settings: ServiceSettings) -> BlobStore:
    provider = settings.storage_provider
    if provider == "gcs":
        if not settings.gcs_bucket_name:
            raise ValueError("GCS_BUCKET_NAME is required when STORAGE_PROVIDER=gcs")
        return GCSBlobStore(
            project_id=settings.gcp_project_id,
            bucket_name=settings.gcs_bucket_name,
            prefix=settings.gcs_prefix,
        )
    if provider == "fs":
        provider = "mem"
    if provider == "mem":
        return InMemoryBlobStore()
    raise ValueError(f"unsupported STORAGE_PROVIDER: {provider}")


def build_control_plane(settings: ServiceSettings) -> PreconversionControlPlane:
    return PreconversionControlPlane(
        config_store=build_config_store(settings),
        job_store=build_job_store(settings),
        job_queue=build_job_queue(settings),
    )
