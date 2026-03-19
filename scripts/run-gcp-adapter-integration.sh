#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${1:-${REPO_DIR}/.env.local.gcp}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: missing env file: ${ENV_FILE}"
  echo "Create it from .env.local.gcp.example"
  exit 1
fi

if [[ ! -x "${REPO_DIR}/.venv/bin/python" ]]; then
  echo "ERROR: missing virtualenv python at ${REPO_DIR}/.venv/bin/python"
  echo "Create .venv and install with: python -m pip install -e \".[prod]\""
  exit 1
fi

set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +a

RUN_GCP_INTEGRATION=1 \
  "${REPO_DIR}/.venv/bin/python" -m unittest tests.test_runtime_gcp_integration

if [[ -n "${POSTGRES_DSN:-}" ]]; then
  RUN_POSTGRES_INTEGRATION=1 \
    "${REPO_DIR}/.venv/bin/python" -m unittest tests.test_runtime_postgres_search_integration
fi
