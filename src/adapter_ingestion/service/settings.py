# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
import os
import re


def _load_dotenv_file(path: str) -> None:
    if not path:
        return
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not key or key in os.environ:
                    continue
                os.environ[key] = value.strip().strip("'").strip('"')
    except OSError:
        return


def _load_default_dotenvs() -> None:
    explicit_env_file = str(os.getenv("PRECONV_ENV_FILE", "") or "").strip()
    if explicit_env_file:
        _load_dotenv_file(explicit_env_file)
    # Compatible with existing Node-style env files.
    _load_dotenv_file(".env")
    _load_dotenv_file(".env.local")


def _getenv(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _getenv_int(name: str, default: int) -> int:
    raw = _getenv(name, str(default))
    try:
        return int(raw)
    except Exception:
        return int(default)


def _split_csv(value: str) -> tuple[str, ...]:
    if not value:
        return ()
    items = [item.strip() for item in str(value).split(",")]
    normalized = [item.lower() for item in items if item.strip()]
    return tuple(normalized)


def _normalize_node_env(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized or "development"


def _environment_resource_profile(node_env: str) -> str:
    normalized = _normalize_node_env(node_env)
    if normalized in {"production", "prod"}:
        return "prod"
    if normalized in {"staging", "stage"}:
        return "staging"
    return "dev"


def _normalize_sector_scope(value: str, vertical: str) -> str:
    explicit = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    if explicit:
        return explicit
    normalized_vertical = str(vertical or "").strip().lower()
    if normalized_vertical in {"vet", "veterinary", "animal", "animal-care"}:
        return "animal"
    if normalized_vertical in {"health", "health-care", "medical"}:
        return "health"
    return "animal"


def _resource_scope_prefix(node_env: str, sector_scope: str) -> str:
    profile = _environment_resource_profile(node_env)
    sector = _normalize_sector_scope(sector_scope, "")
    return f"{profile}-preconvert-{sector}"


def _env_or_profiled_default(name: str, default_suffix: str, node_env: str, sector_scope: str) -> str:
    explicit = _getenv(name)
    if explicit:
        return explicit
    prefix = _resource_scope_prefix(node_env, sector_scope)
    suffix = str(default_suffix or "").strip().strip("-")
    return f"{prefix}-{suffix}" if suffix else prefix


@dataclass(frozen=True)
class ServiceSettings:
    node_env: str
    port: int
    host: str
    db_provider: str
    search_provider: str
    queue_provider: str
    storage_provider: str
    local_data_dir: str
    gcp_project_id: str
    gcp_region: str
    firestore_config_collection: str
    firestore_job_collection: str
    pubsub_topic_id: str
    pubsub_subscription_id: str
    gcs_bucket_name: str
    gcs_prefix: str
    postgres_dsn: str
    postgres_search_table: str
    default_issuer_did: str
    default_audience_did: str
    default_subject_did_prefix: str
    default_species_fhir_file: str
    iclaims_app_id: str
    iclaims_vertical: str
    iclaims_locale: str
    iclaims_code_domain: str
    iclaims_inference_domain: str
    auth_mode: str
    auth_disabled_subjects: tuple[str, ...]
    auth_disabled_devices: tuple[str, ...]
    job_result_ttl_seconds: int


def load_settings() -> ServiceSettings:
    _load_default_dotenvs()
    node_env = _normalize_node_env(_getenv("NODE_ENV", "development"))
    iclaims_vertical = _getenv("ICLAIMS_VERTICAL", "vet")
    sector_scope = _normalize_sector_scope(_getenv("PRECONV_SECTOR_SCOPE", ""), iclaims_vertical)
    auth_mode = _getenv("PRECONV_AUTH_MODE", "parse-only").lower()
    if auth_mode not in {"parse-only", "verify-id-token", "verify-vp-token", "verify-both"}:
        auth_mode = "parse-only"
    return ServiceSettings(
        node_env=node_env,
        port=int(_getenv("PORT", "8080") or "8080"),
        host=_getenv("HOST_INTERNAL_IP", "0.0.0.0"),
        db_provider=_getenv("DB_PROVIDER", "mem").lower(),
        search_provider=_getenv("SEARCH_PROVIDER", "mem").lower(),
        queue_provider=_getenv("QUEUE_PROVIDER", "mem").lower(),
        storage_provider=_getenv("STORAGE_PROVIDER", "mem").lower(),
        local_data_dir=_getenv("PRECONV_LOCAL_DATA_DIR", "./runtime-data"),
        gcp_project_id=_getenv("GCP_PROJECT_ID") or _getenv("FIREBASE_PROJECT_ID"),
        gcp_region=_getenv("GCP_REGION", "europe-west1"),
        firestore_config_collection=_env_or_profiled_default(
            "PRECONV_FIRESTORE_CONFIG_COLLECTION",
            "configs",
            node_env,
            sector_scope,
        ),
        firestore_job_collection=_env_or_profiled_default(
            "PRECONV_FIRESTORE_JOB_COLLECTION",
            "jobs",
            node_env,
            sector_scope,
        ),
        pubsub_topic_id=_env_or_profiled_default(
            "PRECONV_PUBSUB_TOPIC_ID",
            "jobs",
            node_env,
            sector_scope,
        ),
        pubsub_subscription_id=_env_or_profiled_default(
            "PRECONV_PUBSUB_SUBSCRIPTION_ID",
            "jobs-worker",
            node_env,
            sector_scope,
        ),
        gcs_bucket_name=_getenv("GCS_BUCKET_NAME"),
        gcs_prefix=_env_or_profiled_default(
            "PRECONV_GCS_PREFIX",
            "",
            node_env,
            sector_scope,
        ),
        postgres_dsn=_getenv("POSTGRES_DSN"),
        postgres_search_table=_getenv("POSTGRES_SEARCH_TABLE", "resource_search_index"),
        default_issuer_did=_getenv("PRECONV_DEFAULT_ISSUER_DID", "did:web:globaldatacare.es:employee:preconversion"),
        default_audience_did=_getenv("PRECONV_DEFAULT_AUDIENCE_DID", "did:web:globaldatacare.es"),
        default_subject_did_prefix=_getenv("PRECONV_DEFAULT_SUBJECT_DID_PREFIX", "did:web:globaldatacare.es"),
        default_species_fhir_file=_getenv(
            "PRECONV_DEFAULT_SPECIES_FHIR_FILE",
            "./configs/fhir-target-species.template.editable.json",
        ),
        iclaims_app_id=_getenv("ICLAIMS_APP_ID", "vet-claims-api"),
        iclaims_vertical=iclaims_vertical,
        iclaims_locale=_getenv("ICLAIMS_LOCALE", "es"),
        iclaims_code_domain=_getenv("ICLAIMS_CODE_DOMAIN", "none"),
        iclaims_inference_domain=_getenv("ICLAIMS_INFERENCE_DOMAIN", "none"),
        auth_mode=auth_mode,
        auth_disabled_subjects=_split_csv(_getenv("PRECONV_AUTH_DISABLED_SUBJECTS", "")),
        auth_disabled_devices=_split_csv(_getenv("PRECONV_AUTH_DISABLED_DEVICES", "")),
        job_result_ttl_seconds=_getenv_int("PRECONV_JOB_RESULT_TTL_SECONDS", 3600),
    )
