#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${1:-${REPO_DIR}/.env.local}"
PRIVATE_ENV_FILE="${REPO_DIR}/private-cloudsql.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: env file not found: ${ENV_FILE}"
  exit 1
fi

set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +a

if [[ -f "${PRIVATE_ENV_FILE}" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${PRIVATE_ENV_FILE}"
  set +a
fi

SEARCH_PROVIDER="${SEARCH_PROVIDER:-mem}"
DB_PROVIDER="${DB_PROVIDER:-mem}"
QUEUE_PROVIDER="${QUEUE_PROVIDER:-mem}"
STORAGE_PROVIDER="${STORAGE_PROVIDER:-mem}"

if [[ "${SEARCH_PROVIDER}" == "postgresql" && -z "${POSTGRES_DSN:-}" ]]; then
  echo "ERROR: POSTGRES_DSN is required when SEARCH_PROVIDER=postgresql"
  exit 1
fi

if [[ "${DB_PROVIDER}" == "firestore" && -z "${GCP_PROJECT_ID:-}" ]]; then
  echo "ERROR: GCP_PROJECT_ID is required when DB_PROVIDER=firestore"
  exit 1
fi

if [[ "${QUEUE_PROVIDER}" == "pubsub" && -z "${GCP_PROJECT_ID:-}" ]]; then
  echo "ERROR: GCP_PROJECT_ID is required when QUEUE_PROVIDER=pubsub"
  exit 1
fi

if [[ "${STORAGE_PROVIDER}" == "gcs" && ( -z "${GCP_PROJECT_ID:-}" || -z "${GCS_BUCKET_NAME:-}" ) ]]; then
  echo "ERROR: GCP_PROJECT_ID and GCS_BUCKET_NAME are required when STORAGE_PROVIDER=gcs"
  exit 1
fi

echo "Runtime env OK: ${ENV_FILE}"
