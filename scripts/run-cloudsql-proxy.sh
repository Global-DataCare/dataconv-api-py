#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PRIVATE_ENV_FILE="${REPO_DIR}/private-cloudsql.env"
PRIVATE_GCP_CREDENTIALS_FILE="${REPO_DIR}/private-preconversion-runtime-sa.json"

if [[ -f "${PRIVATE_ENV_FILE}" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${PRIVATE_ENV_FILE}"
  set +a
fi

if [[ -f "${PRIVATE_GCP_CREDENTIALS_FILE}" ]]; then
  export GOOGLE_APPLICATION_CREDENTIALS="${PRIVATE_GCP_CREDENTIALS_FILE}"
fi

INSTANCE_CONNECTION_NAME="${POSTGRES_INSTANCE_CONNECTION_NAME:-}"
PROXY_PORT="${CLOUD_SQL_PROXY_PORT:-5432}"

if [[ -z "${INSTANCE_CONNECTION_NAME}" ]]; then
  echo "ERROR: POSTGRES_INSTANCE_CONNECTION_NAME is required"
  exit 1
fi

if command -v cloud-sql-proxy >/dev/null 2>&1; then
  exec cloud-sql-proxy "${INSTANCE_CONNECTION_NAME}" --address 127.0.0.1 --port "${PROXY_PORT}"
fi

if command -v docker >/dev/null 2>&1; then
  exec docker run --rm -it \
    -p "${PROXY_PORT}:${PROXY_PORT}" \
    -v "${HOME}/.config/gcloud:/root/.config/gcloud:ro" \
    gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.18.3 \
    --address 0.0.0.0 \
    --port "${PROXY_PORT}" \
    "${INSTANCE_CONNECTION_NAME}"
fi

echo "ERROR: cloud-sql-proxy binary not found and Docker is unavailable."
exit 1
