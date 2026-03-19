#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${1:-${REPO_DIR}/.env.local}"
PRIVATE_ENV_FILE="${REPO_DIR}/private-cloudsql.env"
PRIVATE_GCP_CREDENTIALS_FILE="${REPO_DIR}/private-preconversion-runtime-sa.json"

"${SCRIPT_DIR}/check-runtime-env.sh" "${ENV_FILE}"

if [[ ! -x "${REPO_DIR}/.venv/bin/preconversion-api" ]]; then
  echo "ERROR: missing ${REPO_DIR}/.venv/bin/preconversion-api"
  echo "Install dependencies first: python -m pip install -e \".[prod]\""
  exit 1
fi

export PRECONV_ENV_FILE="${ENV_FILE}"
if [[ -f "${PRIVATE_ENV_FILE}" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${PRIVATE_ENV_FILE}"
  set +a
fi
if [[ -f "${PRIVATE_GCP_CREDENTIALS_FILE}" ]]; then
  export GOOGLE_APPLICATION_CREDENTIALS="${PRIVATE_GCP_CREDENTIALS_FILE}"
fi
exec "${REPO_DIR}/.venv/bin/preconversion-api"
