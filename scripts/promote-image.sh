#!/usr/bin/env bash
set -euo pipefail

SOURCE_ENV="${1:-staging}"
TARGET_ENV="${2:-production}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE_ENV_FILE="${REPO_DIR}/.env.deploy.${SOURCE_ENV}"
TARGET_ENV_FILE="${REPO_DIR}/.env.deploy.${TARGET_ENV}"

if [[ ! -f "${SOURCE_ENV_FILE}" ]]; then
  echo "ERROR: missing env file: ${SOURCE_ENV_FILE}"
  exit 1
fi
if [[ ! -f "${TARGET_ENV_FILE}" ]]; then
  echo "ERROR: missing env file: ${TARGET_ENV_FILE}"
  exit 1
fi

# shellcheck source=/dev/null
source "${SOURCE_ENV_FILE}"
SOURCE_GCP_PROJECT_ID="${GCP_PROJECT_ID}"
SOURCE_GCP_REGION="${GCP_REGION}"
SOURCE_ARTIFACT_REGISTRY_REPO="${ARTIFACT_REGISTRY_REPO}"
SOURCE_DOCKER_IMAGE_NAME="${DOCKER_IMAGE_NAME}"
SOURCE_DOCKER_IMAGE_TAG="${DOCKER_IMAGE_TAG}"

# shellcheck source=/dev/null
source "${TARGET_ENV_FILE}"
TARGET_GCP_PROJECT_ID="${GCP_PROJECT_ID}"
TARGET_GCP_REGION="${GCP_REGION}"
TARGET_ARTIFACT_REGISTRY_REPO="${ARTIFACT_REGISTRY_REPO}"
TARGET_DOCKER_IMAGE_NAME="${DOCKER_IMAGE_NAME}"
TARGET_DOCKER_IMAGE_TAG="${DOCKER_IMAGE_TAG}"

SOURCE_IMAGE_TAG="${SOURCE_GCP_REGION}-docker.pkg.dev/${SOURCE_GCP_PROJECT_ID}/${SOURCE_ARTIFACT_REGISTRY_REPO}/${SOURCE_DOCKER_IMAGE_NAME}:${SOURCE_DOCKER_IMAGE_TAG}"
TARGET_IMAGE_TAG="${TARGET_GCP_REGION}-docker.pkg.dev/${TARGET_GCP_PROJECT_ID}/${TARGET_ARTIFACT_REGISTRY_REPO}/${TARGET_DOCKER_IMAGE_NAME}:${TARGET_DOCKER_IMAGE_TAG}"

echo "Source image tag: ${SOURCE_IMAGE_TAG}"
echo "Target image tag: ${TARGET_IMAGE_TAG}"

gcloud config set project "${SOURCE_GCP_PROJECT_ID}" >/dev/null

SOURCE_DIGEST_REF="$(gcloud artifacts docker images describe "${SOURCE_IMAGE_TAG}" --format='value(image_summary.fully_qualified_digest)' 2>/dev/null || true)"
if [[ -z "${SOURCE_DIGEST_REF}" ]]; then
  echo "ERROR: unable to resolve digest for source image tag: ${SOURCE_IMAGE_TAG}"
  exit 1
fi

echo "Resolved digest: ${SOURCE_DIGEST_REF}"
gcloud artifacts docker tags add "${SOURCE_DIGEST_REF}" "${TARGET_IMAGE_TAG}" --quiet

echo
echo "Promotion completed."
echo "Use this immutable ref for production deploy:"
echo "${SOURCE_DIGEST_REF}"
echo
echo "Example:"
echo "PRECONV_IMAGE_REF='${SOURCE_DIGEST_REF}' PRECONV_SKIP_BUILD=true ./scripts/deploy-gke.sh ${TARGET_ENV}"

