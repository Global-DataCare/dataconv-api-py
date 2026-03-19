#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROXY_PID=""

is_proxy_up() {
  bash -lc "exec 3<>/dev/tcp/127.0.0.1/5432" >/dev/null 2>&1
}

cleanup() {
  if [[ -n "${PROXY_PID}" ]]; then
    kill "${PROXY_PID}" >/dev/null 2>&1 || true
    wait "${PROXY_PID}" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT

if ! is_proxy_up; then
  "${SCRIPT_DIR}/run-cloudsql-proxy.sh" &
  PROXY_PID="$!"
  for _ in $(seq 1 30); do
    if is_proxy_up; then
      break
    fi
    sleep 1
  done
fi

if ! is_proxy_up; then
  echo "ERROR: Cloud SQL Auth Proxy is not reachable on 127.0.0.1:5432"
  exit 1
fi

exec "${SCRIPT_DIR}/run-api-local.sh" "${1:-${REPO_DIR}/.env.local.gcp}"
