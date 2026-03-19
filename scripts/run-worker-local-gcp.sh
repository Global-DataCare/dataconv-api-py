#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

exec "${SCRIPT_DIR}/run-worker-local.sh" "${1:-${REPO_DIR}/.env.local.gcp}"
