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


def _split_csv_raw(value: str) -> tuple[str, ...]:
    if not value:
        return ()
    items = [item.strip() for item in str(value).split(",")]
    return tuple(item for item in items if item)


def _parse_supported_values(value: str, *, upper: bool = False) -> tuple[str, ...]:
    raw = str(value or "").strip()
    if not raw:
        return ("*",)
    tokens: list[str] = []
    for item in raw.split(","):
        token = str(item or "").strip()
        if not token:
            continue
        if token == "*":
            return ("*",)
        normalized = token.upper() if upper else token.lower()
        tokens.append(normalized)
    return tuple(tokens) if tokens else ("*",)


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
    auth_disabled_subjects: tuple[str, ...]
    auth_disabled_devices: tuple[str, ...]
    demo_mode: bool
    exchange_session_token_secret: str
    exchange_session_token_ttl_seconds: int
    exchange_oidc_issuer: str
    exchange_oidc_audience: str
    exchange_oidc_allowed_issuers: tuple[str, ...]
    exchange_oidc_allowed_audiences: tuple[str, ...]
    exchange_oidc_jwks_cache_ttl_seconds: int
    exchange_default_allowed_scopes: str
    exchange_allow_insecure_assertions: bool
    exchange_allow_api_key: bool
    exchange_api_keys: tuple[str, ...]
    exchange_api_key_subject_default: str
    exchange_api_key_org_default: str
    job_result_ttl_seconds: int
    supported_jurisdictions: tuple[str, ...] = ("*",)
    supported_sectors: tuple[str, ...] = ("*",)
    exchange_allow_api_key_exception: bool = False


def load_settings() -> ServiceSettings:
    _load_default_dotenvs()
    node_env = _normalize_node_env(_getenv("NODE_ENV", "development"))
    iclaims_vertical = _getenv("ICLAIMS_VERTICAL", "vet")
    sector_scope = _normalize_sector_scope(
        _getenv("PRECONV_DATASPACE_ID", "") or _getenv("PRECONV_SECTOR_SCOPE", ""),
        iclaims_vertical,
    )
    exchange_allow_insecure_assertions = _getenv("EXCHANGE_ALLOW_INSECURE_ASSERTIONS", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    exchange_allow_api_key = _getenv("EXCHANGE_ALLOW_API_KEY", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    exchange_allow_api_key_exception = _getenv("EXCHANGE_ALLOW_API_KEY_EXCEPTION", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return ServiceSettings(
        node_env=node_env,
        port=int(_getenv("PORT", "") or _getenv("LOCAL_PORT", "8080") or "8080"),
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
        auth_disabled_subjects=_split_csv(_getenv("PRECONV_AUTH_DISABLED_SUBJECTS", "")),
        auth_disabled_devices=_split_csv(_getenv("PRECONV_AUTH_DISABLED_DEVICES", "")),
        demo_mode=_getenv("DEMO_MODE", "false").lower() in {"1", "true", "yes", "on"},
        exchange_session_token_secret=_getenv("EXCHANGE_SESSION_TOKEN_SECRET", "dev-session-secret-change-me"),
        exchange_session_token_ttl_seconds=_getenv_int("EXCHANGE_SESSION_TOKEN_TTL_SECONDS", 900),
        exchange_oidc_issuer=_getenv("EXCHANGE_OIDC_ISSUER", ""),
        exchange_oidc_audience=_getenv("EXCHANGE_OIDC_AUDIENCE", ""),
        exchange_oidc_allowed_issuers=_split_csv_raw(_getenv("EXCHANGE_OIDC_ALLOWED_ISSUERS", "")),
        exchange_oidc_allowed_audiences=_split_csv_raw(_getenv("EXCHANGE_OIDC_ALLOWED_AUDIENCES", "")),
        exchange_oidc_jwks_cache_ttl_seconds=_getenv_int("EXCHANGE_OIDC_JWKS_CACHE_TTL_SECONDS", 3600),
        exchange_default_allowed_scopes=_getenv("EXCHANGE_DEFAULT_ALLOWED_SCOPES", "dataconv.upload"),
        exchange_allow_insecure_assertions=exchange_allow_insecure_assertions,
        exchange_allow_api_key=exchange_allow_api_key,
        exchange_api_keys=_split_csv(_getenv("EXCHANGE_API_KEYS", "")),
        exchange_api_key_subject_default=_getenv("EXCHANGE_API_KEY_SUBJECT_DEFAULT", ""),
        exchange_api_key_org_default=_getenv("EXCHANGE_API_KEY_ORG_DEFAULT", ""),
        job_result_ttl_seconds=_getenv_int("PRECONV_JOB_RESULT_TTL_SECONDS", 3600),
        supported_jurisdictions=_parse_supported_values(_getenv("SUPPORTED_JURISDICTIONS", "*"), upper=True),
        supported_sectors=_parse_supported_values(_getenv("SUPPORTED_SECTORS", "*"), upper=False),
        exchange_allow_api_key_exception=exchange_allow_api_key_exception,
    )
