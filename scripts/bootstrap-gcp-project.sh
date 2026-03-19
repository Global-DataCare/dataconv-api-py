#!/usr/bin/env bash

set -euo pipefail

require_var() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: ${name}" >&2
    exit 1
  fi
}

add_project_role() {
  local member="$1"
  local role="$2"

  gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
    --member="user:${member}" \
    --role="${role}" \
    --quiet >/dev/null
}

project_exists() {
  gcloud projects describe "${GCP_PROJECT_ID}" >/dev/null 2>&1
}

artifact_repo_exists() {
  gcloud artifacts repositories describe "${ARTIFACT_REGISTRY_REPO}" \
    --location="${GCP_REGION}" >/dev/null 2>&1
}

bucket_exists() {
  gcloud storage buckets describe "gs://${GCS_BUCKET_NAME}" >/dev/null 2>&1
}

firestore_database_exists() {
  gcloud firestore databases describe --database="(default)" \
    --project="${GCP_PROJECT_ID}" >/dev/null 2>&1
}

cluster_exists() {
  gcloud container clusters describe "${GKE_CLUSTER_NAME}" \
    --region="${GCP_REGION}" >/dev/null 2>&1
}

namespace_exists() {
  local namespace="$1"
  kubectl get namespace "${namespace}" >/dev/null 2>&1
}

budget_exists() {
  local display_name="$1"

  gcloud billing budgets list \
    --billing-account="${BILLING_ACCOUNT_ID}" \
    --filter="displayName=${display_name}" \
    --format="value(displayName)" | grep -Fxq "${display_name}"
}

require_var GCP_PROJECT_ID
require_var GCP_PROJECT_NAME
require_var BILLING_ACCOUNT_ID
require_var GCP_REGION
require_var GKE_CLUSTER_NAME
require_var PRECONV_MANAGER_EMAIL
require_var PRECONV_OPERATOR_EMAILS

FOLDER_ID="${FOLDER_ID:-}"
ORGANIZATION_ID="${ORGANIZATION_ID:-}"
ARTIFACT_REGISTRY_REPO="${ARTIFACT_REGISTRY_REPO:-onehealth-apps}"
GKE_NODE_MACHINE_TYPE="${GKE_NODE_MACHINE_TYPE:-e2-medium}"
GKE_NODES_PER_ZONE="${GKE_NODES_PER_ZONE:-1}"
K8S_NAMESPACES="${K8S_NAMESPACES:-shared animal health}"
GCS_BUCKET_NAME="${GCS_BUCKET_NAME:-${GCP_PROJECT_ID}}"
GCS_BUCKET_LOCATION="${GCS_BUCKET_LOCATION:-${GCP_REGION}}"
FIRESTORE_LOCATION="${FIRESTORE_LOCATION:-}"
BUDGET_AMOUNT="${BUDGET_AMOUNT:-}"
BUDGET_DISPLAY_NAME="${BUDGET_DISPLAY_NAME:-budget-${GCP_PROJECT_ID}}"

if [[ -n "${FOLDER_ID}" && -n "${ORGANIZATION_ID}" ]]; then
  echo "Use either FOLDER_ID or ORGANIZATION_ID, not both." >&2
  exit 1
fi

if ! project_exists; then
  create_args=(
    "${GCP_PROJECT_ID}"
    "--name=${GCP_PROJECT_NAME}"
    "--set-as-default"
  )

  if [[ -n "${FOLDER_ID}" ]]; then
    create_args+=("--folder=${FOLDER_ID}")
  fi

  if [[ -n "${ORGANIZATION_ID}" ]]; then
    create_args+=("--organization=${ORGANIZATION_ID}")
  fi

  gcloud projects create "${create_args[@]}"
else
  gcloud config set project "${GCP_PROJECT_ID}" >/dev/null
fi

gcloud billing projects link "${GCP_PROJECT_ID}" \
  --billing-account="${BILLING_ACCOUNT_ID}" >/dev/null

gcloud services enable \
  compute.googleapis.com \
  container.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  firestore.googleapis.com \
  pubsub.googleapis.com \
  storage.googleapis.com \
  --project="${GCP_PROJECT_ID}" >/dev/null

MANAGER_ROLES=(
  "roles/container.admin"
  "roles/compute.admin"
  "roles/iam.serviceAccountUser"
  "roles/artifactregistry.admin"
  "roles/datastore.owner"
  "roles/pubsub.admin"
  "roles/storage.admin"
  "roles/logging.viewer"
  "roles/monitoring.viewer"
)

OPERATOR_ROLES=(
  "roles/container.developer"
  "roles/artifactregistry.writer"
  "roles/logging.viewer"
  "roles/monitoring.viewer"
)

for role in "${MANAGER_ROLES[@]}"; do
  add_project_role "${PRECONV_MANAGER_EMAIL}" "${role}"
done

for email in ${PRECONV_OPERATOR_EMAILS}; do
  for role in "${OPERATOR_ROLES[@]}"; do
    add_project_role "${email}" "${role}"
  done
done

gcloud config set project "${GCP_PROJECT_ID}" >/dev/null

if ! artifact_repo_exists; then
  gcloud artifacts repositories create "${ARTIFACT_REGISTRY_REPO}" \
    --location="${GCP_REGION}" \
    --repository-format=docker \
    --description="Docker images for api-convert-onehealth"
fi

if ! bucket_exists; then
  gcloud storage buckets create "gs://${GCS_BUCKET_NAME}" \
    --location="${GCS_BUCKET_LOCATION}" \
    --uniform-bucket-level-access
fi

if [[ -n "${FIRESTORE_LOCATION}" ]] && ! firestore_database_exists; then
  gcloud firestore databases create \
    --database="(default)" \
    --location="${FIRESTORE_LOCATION}" \
    --type=firestore-native >/dev/null
fi

if ! cluster_exists; then
  gcloud container clusters create "${GKE_CLUSTER_NAME}" \
    --region="${GCP_REGION}" \
    --release-channel=regular \
    --machine-type="${GKE_NODE_MACHINE_TYPE}" \
    --num-nodes="${GKE_NODES_PER_ZONE}"
fi

gcloud container clusters get-credentials "${GKE_CLUSTER_NAME}" \
  --region="${GCP_REGION}" \
  --project="${GCP_PROJECT_ID}" >/dev/null

for namespace in ${K8S_NAMESPACES}; do
  if ! namespace_exists "${namespace}"; then
    kubectl create namespace "${namespace}" >/dev/null
  fi
done

if [[ -n "${BUDGET_AMOUNT}" ]] && ! budget_exists "${BUDGET_DISPLAY_NAME}"; then
  gcloud billing budgets create \
    --billing-account="${BILLING_ACCOUNT_ID}" \
    --display-name="${BUDGET_DISPLAY_NAME}" \
    --budget-amount="${BUDGET_AMOUNT}" \
    --filter-projects="projects/${GCP_PROJECT_ID}" \
    --calendar-period=month \
    --threshold-rule=percent=0.50 \
    --threshold-rule=percent=0.75 \
    --threshold-rule=percent=0.90 \
    --threshold-rule=percent=1.00 >/dev/null
fi

echo "Bootstrap finished."
echo "Project: ${GCP_PROJECT_ID}"
echo "Region: ${GCP_REGION}"
echo "Cluster: ${GKE_CLUSTER_NAME}"
echo "Cluster type: Standard regional"
echo "Machine type: ${GKE_NODE_MACHINE_TYPE}"
echo "Nodes per zone: ${GKE_NODES_PER_ZONE}"
echo "Total nodes in region: $(( GKE_NODES_PER_ZONE * 3 ))"
echo "Namespaces: ${K8S_NAMESPACES}"
echo "Artifact Registry: ${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY_REPO}"
echo "Bucket: gs://${GCS_BUCKET_NAME}"
if [[ -n "${FIRESTORE_LOCATION}" ]]; then
  echo "Firestore location: ${FIRESTORE_LOCATION}"
else
  echo "Firestore location: not created by script"
fi
