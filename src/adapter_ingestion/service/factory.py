# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import base64
import os

from ..runtime import BlobStore, ConfigStore, ISearchRepository, IVaultRepository, JobQueue, JobStore, PreconversionControlPlane
from ..runtime.adapters import (
    FirestoreConfigStore,
    FirestoreJobStore,
    FirestoreSubjectLinkRecordStore,
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
from ..subject_links import InMemorySubjectLinkRecordStore, ProtectedSubjectLinkStore
from ..ai import HttpCodingModelClient, HttpTerminologyClient, TerminologyCodingAssistant, UnrankedCodingRanker
from ..ai.base import NoopCodingAssistant
from ..ai.http import google_audience_token_provider
from .coding_review import NoopCodingFeedbackSink
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


def build_subject_link_store(settings: ServiceSettings) -> ProtectedSubjectLinkStore:
    if not settings.subject_link_protection_key and settings.db_provider == "firestore":
        raise ValueError("SUBJECT_LINK_PROTECTION_KEY is required")
    provider = settings.db_provider
    if provider == "firestore":
        records = FirestoreSubjectLinkRecordStore(
            project_id=settings.gcp_project_id,
            collection=settings.firestore_subject_link_collection,
        )
    elif provider in {"mem", "fs"}:
        records = InMemorySubjectLinkRecordStore()
    else:
        raise ValueError(f"unsupported DB_PROVIDER for subject links: {provider}")
    return ProtectedSubjectLinkStore(
        records=records,
        key_base64url=settings.subject_link_protection_key
        or base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("="),
        key_version=settings.subject_link_key_version,
    )


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


def _coding_model_client(settings: ServiceSettings):
    if not settings.coding_model_base_url:
        return None
    token_provider = (
        google_audience_token_provider(settings.coding_model_audience)
        if settings.coding_model_audience and not settings.coding_model_token
        else None
    )
    return HttpCodingModelClient(
        base_url=settings.coding_model_base_url,
        token=settings.coding_model_token,
        token_provider=token_provider,
        model=settings.coding_model_id,
        timeout_seconds=settings.coding_model_timeout_seconds,
    )


def build_coding_assistant(settings: ServiceSettings, context):
    model = _coding_model_client(settings)
    if not settings.terminology_base_url:
        return NoopCodingAssistant()
    if model is None:
        model = UnrankedCodingRanker()
    terminology = HttpTerminologyClient(
        base_url=settings.terminology_base_url,
        token=settings.terminology_token,
        timeout_seconds=settings.terminology_timeout_seconds,
    )
    return TerminologyCodingAssistant(context=context, terminology=terminology, ranker=model)


def build_coding_feedback_sink(settings: ServiceSettings):
    return _coding_model_client(settings) or NoopCodingFeedbackSink()
