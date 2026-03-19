#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_NAME="${1:-staging}"

exec "${SCRIPT_DIR}/scripts/deploy-gke.sh" "${ENV_NAME}"
