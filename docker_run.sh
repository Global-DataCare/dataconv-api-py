#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="${IMAGE_NAME:-preconversion-api:local-0.6.2}"
PROCESS_MODE="${PROCESS_MODE:-api}"
CONTAINER_NAME="${CONTAINER_NAME:-preconversion-${PROCESS_MODE}}"
PRIVATE_ENV_FILE="${SCRIPT_DIR}/private-cloudsql.env"
GOOGLE_CREDENTIALS_FILE="${SCRIPT_DIR}/gcp-service-account.json"
PRIVATE_GCP_CREDENTIALS_FILE="${SCRIPT_DIR}/private-preconversion-runtime-sa.json"

resolve_env_file() {
  local selector="$1"

  if [[ -z "${selector}" || "${selector}" == "local" ]]; then
    echo "${SCRIPT_DIR}/.env.local"
    return 0
  fi

  if [[ "${selector}" == "local-gcp" || "${selector}" == "gcp" ]]; then
    echo "${SCRIPT_DIR}/.env.local.gcp"
    return 0
  fi

  if [[ "${selector}" =~ ^(staging|production)$ ]]; then
    echo "${SCRIPT_DIR}/.env.deploy.${selector}"
    return 0
  fi

  if [[ -f "${selector}" ]]; then
    echo "${selector}"
    return 0
  fi

  if [[ -f "${SCRIPT_DIR}/${selector}" ]]; then
    echo "${SCRIPT_DIR}/${selector}"
    return 0
  fi

  return 1
}

extract_env_value() {
  local file="$1"
  local key="$2"
  awk -F= -v k="$key" '
    /^[[:space:]]*#/ { next }
    $1 == k {
      value=$2
      sub(/\r$/, "", value)
      print value
      exit
    }
  ' "$file"
}

ENV_SELECTOR="${1:-local}"
if ! ENV_FILE="$(resolve_env_file "${ENV_SELECTOR}")"; then
  echo "ERROR: unable to resolve env file for '${ENV_SELECTOR}'"
  echo "Usage: ./docker_run.sh [local|local-gcp|staging|production|/path/to/env]"
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: env file not found: ${ENV_FILE}"
  exit 1
fi

"${SCRIPT_DIR}/scripts/check-runtime-env.sh" "${ENV_FILE}"

echo "Checking Docker daemon..."
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker is not running."
  exit 1
fi

if ! docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1; then
  echo "ERROR: image '${IMAGE_NAME}' not found."
  echo "Run ./docker_build_local.sh first."
  exit 1
fi

APP_PORT="$(extract_env_value "${ENV_FILE}" "PORT")"
APP_PORT="${APP_PORT:-8080}"
HOST_PORT="${HOST_PORT:-${APP_PORT}}"

COMMAND=()
case "${PROCESS_MODE}" in
  api)
    COMMAND=()
    ;;
  worker)
    COMMAND=("preconversion-worker")
    ;;
  cleanup)
    COMMAND=("preconversion-cleanup" "--dry-run" "--pretty")
    ;;
  *)
    echo "ERROR: unsupported PROCESS_MODE='${PROCESS_MODE}'. Use api, worker or cleanup."
    exit 1
    ;;
esac

echo "Running container"
echo "  Image:      ${IMAGE_NAME}"
echo "  Container:  ${CONTAINER_NAME}"
echo "  Env file:   ${ENV_FILE}"
echo "  Mode:       ${PROCESS_MODE}"

docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

DOCKER_ARGS=(
  --name "${CONTAINER_NAME}"
  --env-file "${ENV_FILE}"
)

if [[ -f "${PRIVATE_ENV_FILE}" ]]; then
  DOCKER_ARGS+=(--env-file "${PRIVATE_ENV_FILE}")
fi

if [[ "${ENV_SELECTOR}" == "local-gcp" || "${ENV_SELECTOR}" == "gcp" ]]; then
  if [[ -f "${PRIVATE_GCP_CREDENTIALS_FILE}" ]]; then
    DOCKER_ARGS+=(
      -v "${PRIVATE_GCP_CREDENTIALS_FILE}:/app/gcp-service-account.json:ro"
      -e "GOOGLE_APPLICATION_CREDENTIALS=/app/gcp-service-account.json"
    )
  elif [[ -f "${GOOGLE_CREDENTIALS_FILE}" ]]; then
    DOCKER_ARGS+=(
      -v "${GOOGLE_CREDENTIALS_FILE}:/app/gcp-service-account.json:ro"
      -e "GOOGLE_APPLICATION_CREDENTIALS=/app/gcp-service-account.json"
    )
  fi
fi

if [[ "${PROCESS_MODE}" == "api" ]]; then
  docker run -d \
    "${DOCKER_ARGS[@]}" \
    -p "${HOST_PORT}:${APP_PORT}" \
    "${IMAGE_NAME}"
  echo "Container started: ${CONTAINER_NAME}"
  echo "Health check URL: http://127.0.0.1:${HOST_PORT}/healthz"
else
  docker run -d \
    "${DOCKER_ARGS[@]}" \
    "${IMAGE_NAME}" \
    "${COMMAND[@]}"
  echo "Container started: ${CONTAINER_NAME}"
fi
