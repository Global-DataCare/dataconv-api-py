#!/usr/bin/env bash
set -euo pipefail

COMMAND=("$@")
if [[ "${#COMMAND[@]}" -eq 0 ]]; then
  COMMAND=("preconversion-api")
fi

PROXY_PID=""

wait_for_proxy() {
  local retries=30
  while (( retries > 0 )); do
    if bash -lc "exec 3<>/dev/tcp/127.0.0.1/5432" >/dev/null 2>&1; then
      return 0
    fi
    retries=$((retries - 1))
    sleep 1
  done
  return 1
}

cleanup() {
  if [[ -n "${PROXY_PID}" ]]; then
    kill "${PROXY_PID}" >/dev/null 2>&1 || true
    wait "${PROXY_PID}" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT

if [[ "${SEARCH_PROVIDER:-mem}" == "postgresql" && -n "${POSTGRES_INSTANCE_CONNECTION_NAME:-}" ]]; then
  cloud-sql-proxy "${POSTGRES_INSTANCE_CONNECTION_NAME}" --address 127.0.0.1 --port 5432 &
  PROXY_PID="$!"
  if ! wait_for_proxy; then
    echo "ERROR: Cloud SQL Auth Proxy did not become ready on 127.0.0.1:5432"
    exit 1
  fi
fi

exec "${COMMAND[@]}"
