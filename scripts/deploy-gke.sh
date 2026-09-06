#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-production}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${REPO_DIR}/.env.deploy.${ENV_NAME}"
PRIVATE_ENV_FILE="${REPO_DIR}/private-cloudsql.${ENV_NAME}.env"
LEGACY_PRIVATE_ENV_FILE="${REPO_DIR}/private-cloudsql.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: missing env file: ${ENV_FILE}"
  echo "Create it from .env.deploy.${ENV_NAME}.example"
  exit 1
fi

if [[ -f "${PRIVATE_ENV_FILE}" ]]; then
  # shellcheck source=/dev/null
  source "${PRIVATE_ENV_FILE}"
elif [[ "${ENV_NAME}" == "staging" || "${ENV_NAME}" == "production" ]] && [[ -f "${LEGACY_PRIVATE_ENV_FILE}" ]]; then
  # Backward compatibility for the original Europe-only deployment file. New
  # environments must never inherit another deployment's Cloud SQL target.
  # shellcheck source=/dev/null
  source "${LEGACY_PRIVATE_ENV_FILE}"
fi
# Load deployment-specific secrets first so the public profile may require
# them with `${NAME:?message}` without storing their values in the profile.
# shellcheck source=/dev/null
source "${ENV_FILE}"

required_vars=(
  GCP_PROJECT_ID
  GCP_REGION
  K8S_CLUSTER
  K8S_NAMESPACE
  DOCKER_IMAGE_NAME
  DOCKER_IMAGE_TAG
  ARTIFACT_REGISTRY_REPO
  GCS_BUCKET_NAME
  PRECONV_GCP_SERVICE_ACCOUNT
  SUBJECT_LINK_PROTECTION_KEY
  PRECONV_ICA_BASE_URL
  PRECONV_ICA_API_KEY
  EXCHANGE_OIDC_ISSUER
  EXCHANGE_OIDC_AUDIENCE
  EXCHANGE_SESSION_TOKEN_SECRET
  SMART_GW_ALLOWED_ISSUERS
  SMART_GW_EXPECTED_AUDIENCES
  SMART_GW_ISSUER_TENANT_BINDINGS
)

missing=0
for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "ERROR: ${var_name} is required in ${ENV_FILE}"
    missing=1
  fi
done
if [[ "${missing}" -ne 0 ]]; then
  exit 1
fi

SEARCH_PROVIDER="${SEARCH_PROVIDER:-mem}"
POSTGRES_DSN="${POSTGRES_DSN:-}"
POSTGRES_SEARCH_TABLE="${POSTGRES_SEARCH_TABLE:-resource_search_index}"
POSTGRES_INSTANCE_CONNECTION_NAME="${POSTGRES_INSTANCE_CONNECTION_NAME:-}"

if [[ "${SEARCH_PROVIDER}" == "postgresql" && -z "${POSTGRES_DSN}" ]]; then
  echo "ERROR: POSTGRES_DSN is required in ${ENV_FILE} when SEARCH_PROVIDER=postgresql"
  exit 1
fi

IMAGE_URI="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY_REPO}/${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG}"
INGRESS_HOST="${PRECONV_INGRESS_HOST-preconversion.example.globaldatacare.es}"
INGRESS_STATIC_IP_NAME="${PRECONV_INGRESS_STATIC_IP_NAME:-}"
MANAGED_CERT_NAME="${PRECONV_MANAGED_CERT_NAME:-}"
PRE_SHARED_CERT_NAME="${PRECONV_PRE_SHARED_CERT_NAME:-}"
TLS_SECRET_NAME="${PRECONV_TLS_SECRET_NAME:-}"
DISABLE_HTTP="${PRECONV_DISABLE_HTTP:-false}"
TERMINOLOGY_INGRESS_ENABLED="${PRECONV_TERMINOLOGY_INGRESS_ENABLED:-false}"
TERMINOLOGY_INGRESS_SERVICE_NAME="${PRECONV_TERMINOLOGY_INGRESS_SERVICE_NAME:-}"
TERMINOLOGY_INGRESS_SERVICE_PORT="${PRECONV_TERMINOLOGY_INGRESS_SERVICE_PORT:-}"
IMAGE_REF="${PRECONV_IMAGE_REF:-}"
SKIP_BUILD="${PRECONV_SKIP_BUILD:-false}"
ICLAIMS_APP_ID_RAW="${ICLAIMS_APP_ID:-vet-claims-api}"
ICLAIMS_APP_ID="$(echo "${ICLAIMS_APP_ID_RAW}" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9-]+/-/g; s/^-+//; s/-+$//; s/-+/-/g')"
ICLAIMS_VERTICAL="${ICLAIMS_VERTICAL:-vet}"
ICLAIMS_LOCALE="${ICLAIMS_LOCALE:-es}"
ICLAIMS_CODE_DOMAIN="${ICLAIMS_CODE_DOMAIN:-none}"
ICLAIMS_INFERENCE_DOMAIN="${ICLAIMS_INFERENCE_DOMAIN:-none}"
PRECONV_DATASPACE_ID="${PRECONV_DATASPACE_ID:-${PRECONV_SECTOR_SCOPE:-animal}}"
CLEANUP_SCHEDULE="${PRECONV_CLEANUP_SCHEDULE:-*/15 * * * *}"
CLEANUP_SCHEDULE_ESCAPED="$(printf '%s' "${CLEANUP_SCHEDULE}" | sed -e 's/[\/&]/\\&/g')"
API_REPLICAS="${API_REPLICAS:-2}"
WORKER_REPLICAS="${WORKER_REPLICAS:-2}"
API_MAX_SURGE="${API_MAX_SURGE:-25%}"
API_MAX_UNAVAILABLE="${API_MAX_UNAVAILABLE:-25%}"
WORKER_MAX_SURGE="${WORKER_MAX_SURGE:-25%}"
WORKER_MAX_UNAVAILABLE="${WORKER_MAX_UNAVAILABLE:-25%}"
HPA_MIN_REPLICAS="${HPA_MIN_REPLICAS:-2}"
HPA_MAX_REPLICAS="${HPA_MAX_REPLICAS:-10}"

SERVICE_ACCOUNT_NAME="${ICLAIMS_APP_ID}-sa"
CONFIGMAP_NAME="${ICLAIMS_APP_ID}-config"
SECRET_NAME="${ICLAIMS_APP_ID}-secrets"
DEPLOY_API_NAME="${ICLAIMS_APP_ID}"
DEPLOY_WORKER_NAME="${ICLAIMS_APP_ID}-worker"
SERVICE_NAME="${DEPLOY_API_NAME}"

tls_mode_count=0
[[ -n "${MANAGED_CERT_NAME}" ]] && tls_mode_count=$((tls_mode_count + 1))
[[ -n "${PRE_SHARED_CERT_NAME}" ]] && tls_mode_count=$((tls_mode_count + 1))
[[ -n "${TLS_SECRET_NAME}" ]] && tls_mode_count=$((tls_mode_count + 1))

if [[ "${tls_mode_count}" -gt 1 ]]; then
  echo "ERROR: choose only one TLS mode: PRECONV_MANAGED_CERT_NAME, PRECONV_PRE_SHARED_CERT_NAME or PRECONV_TLS_SECRET_NAME."
  exit 1
fi

if [[ "${DISABLE_HTTP}" == "true" && "${tls_mode_count}" -eq 0 ]]; then
  echo "ERROR: PRECONV_DISABLE_HTTP=true requires a TLS mode."
  exit 1
fi

if [[ -n "${MANAGED_CERT_NAME}" && -z "${INGRESS_HOST}" ]]; then
  echo "ERROR: PRECONV_MANAGED_CERT_NAME requires PRECONV_INGRESS_HOST."
  exit 1
fi

if [[ "${DISABLE_HTTP}" == "true" && -n "${MANAGED_CERT_NAME}" ]]; then
  echo "ERROR: PRECONV_DISABLE_HTTP=true is not supported together with PRECONV_MANAGED_CERT_NAME in this deploy flow."
  echo "Apply the Ingress first, wait until the load balancer is provisioned, and only then disable HTTP manually if needed."
  exit 1
fi

if [[ "${TERMINOLOGY_INGRESS_ENABLED}" != "true" && "${TERMINOLOGY_INGRESS_ENABLED}" != "false" ]]; then
  echo "ERROR: PRECONV_TERMINOLOGY_INGRESS_ENABLED must be true or false."
  exit 1
fi

if [[ "${TERMINOLOGY_INGRESS_ENABLED}" == "true" ]]; then
  if [[ -z "${TERMINOLOGY_INGRESS_SERVICE_NAME}" || -z "${TERMINOLOGY_INGRESS_SERVICE_PORT}" ]]; then
    echo "ERROR: PRECONV_TERMINOLOGY_INGRESS_ENABLED=true requires PRECONV_TERMINOLOGY_INGRESS_SERVICE_NAME and PRECONV_TERMINOLOGY_INGRESS_SERVICE_PORT."
    exit 1
  fi
  if [[ ${#TERMINOLOGY_INGRESS_SERVICE_NAME} -gt 63 || ! "${TERMINOLOGY_INGRESS_SERVICE_NAME}" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]]; then
    echo "ERROR: PRECONV_TERMINOLOGY_INGRESS_SERVICE_NAME must be a Kubernetes DNS label."
    exit 1
  fi
  if [[ ! "${TERMINOLOGY_INGRESS_SERVICE_PORT}" =~ ^[0-9]{1,5}$ ]] || (( 10#${TERMINOLOGY_INGRESS_SERVICE_PORT} < 1 || 10#${TERMINOLOGY_INGRESS_SERVICE_PORT} > 65535 )); then
    echo "ERROR: PRECONV_TERMINOLOGY_INGRESS_SERVICE_PORT must be an integer from 1 to 65535."
    exit 1
  fi
  TERMINOLOGY_INGRESS_SERVICE_PORT="$((10#${TERMINOLOGY_INGRESS_SERVICE_PORT}))"
fi

render_ingress_manifest() {
  cat <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ${DEPLOY_API_NAME}
  namespace: ${K8S_NAMESPACE}
  annotations:
    kubernetes.io/ingress.class: "gce"
EOF

  if [[ -n "${INGRESS_STATIC_IP_NAME}" ]]; then
    echo "    kubernetes.io/ingress.global-static-ip-name: \"${INGRESS_STATIC_IP_NAME}\""
  fi

  if [[ -n "${MANAGED_CERT_NAME}" ]]; then
    echo "    networking.gke.io/managed-certificates: \"${MANAGED_CERT_NAME}\""
  fi

  if [[ -n "${PRE_SHARED_CERT_NAME}" ]]; then
    echo "    ingress.gcp.kubernetes.io/pre-shared-cert: \"${PRE_SHARED_CERT_NAME}\""
  fi

  if [[ "${DISABLE_HTTP}" == "true" ]]; then
    echo "    kubernetes.io/ingress.allow-http: \"false\""
  fi

  cat <<EOF
spec:
EOF

  if [[ -n "${TLS_SECRET_NAME}" ]]; then
    cat <<EOF
  tls:
    - secretName: ${TLS_SECRET_NAME}
EOF
  fi

  cat <<EOF
  rules:
    -
EOF

  if [[ -n "${INGRESS_HOST}" ]]; then
    echo "      host: ${INGRESS_HOST}"
  fi

  cat <<EOF
      http:
        paths:
EOF

  if [[ "${TERMINOLOGY_INGRESS_ENABLED}" == "true" ]]; then
    cat <<EOF
          - path: /v1/terminology
            pathType: Prefix
            backend:
              service:
                name: ${TERMINOLOGY_INGRESS_SERVICE_NAME}
                port:
                  number: ${TERMINOLOGY_INGRESS_SERVICE_PORT}
EOF
  fi

  cat <<EOF
          - path: /
            pathType: Prefix
            backend:
              service:
                name: ${DEPLOY_API_NAME}
                port:
                  number: 80
EOF
}

if [[ -n "${IMAGE_REF}" ]]; then
  echo "Using provided image ref: ${IMAGE_REF}"
else
  echo "Using image tag: ${IMAGE_URI}"
fi
echo "iClaims app id: ${ICLAIMS_APP_ID}"
echo "Deploying namespace: ${K8S_NAMESPACE}"
echo

gcloud config set project "${GCP_PROJECT_ID}" >/dev/null
gcloud container clusters get-credentials "${K8S_CLUSTER}" --region "${GCP_REGION}"
gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev" -q

if [[ -z "${IMAGE_REF}" ]]; then
  if [[ "${SKIP_BUILD}" == "true" ]]; then
    echo "ERROR: PRECONV_SKIP_BUILD=true requires PRECONV_IMAGE_REF to be set."
    exit 1
  fi
  docker build -t "${IMAGE_URI}" "${REPO_DIR}"
  docker push "${IMAGE_URI}"
  IMAGE_REF="$(docker image inspect --format='{{index .RepoDigests 0}}' "${IMAGE_URI}" 2>/dev/null || true)"
  if [[ -z "${IMAGE_REF}" ]]; then
    IMAGE_REF="${IMAGE_URI}"
  fi
fi

kubectl apply -f <(sed "s/name: preconversion/name: ${K8S_NAMESPACE}/g" "${REPO_DIR}/k8s/namespace.yaml")

kubectl -n "${K8S_NAMESPACE}" create serviceaccount "${SERVICE_ACCOUNT_NAME}" --dry-run=client -o yaml \
  | kubectl apply -f -
kubectl -n "${K8S_NAMESPACE}" annotate serviceaccount "${SERVICE_ACCOUNT_NAME}" \
  "iam.gke.io/gcp-service-account=${PRECONV_GCP_SERVICE_ACCOUNT}" --overwrite

kubectl -n "${K8S_NAMESPACE}" create configmap "${CONFIGMAP_NAME}" \
  --from-literal=NODE_ENV="${NODE_ENV:-production}" \
  --from-literal=PORT="${PORT:-8080}" \
  --from-literal=HOST_INTERNAL_IP="${HOST_INTERNAL_IP:-0.0.0.0}" \
  --from-literal=PRECONV_DATASPACE_ID="${PRECONV_DATASPACE_ID}" \
  --from-literal=DB_PROVIDER="${DB_PROVIDER:-firestore}" \
  --from-literal=SEARCH_PROVIDER="${SEARCH_PROVIDER}" \
  --from-literal=QUEUE_PROVIDER="${QUEUE_PROVIDER:-pubsub}" \
  --from-literal=STORAGE_PROVIDER="${STORAGE_PROVIDER:-gcs}" \
  --from-literal=NETWORK_MODE="${NETWORK_MODE:-network}" \
  --from-literal=PRECONV_FIRESTORE_CONFIG_COLLECTION="${PRECONV_FIRESTORE_CONFIG_COLLECTION:-}" \
  --from-literal=PRECONV_FIRESTORE_JOB_COLLECTION="${PRECONV_FIRESTORE_JOB_COLLECTION:-}" \
  --from-literal=PRECONV_FIRESTORE_SUBJECT_LINK_COLLECTION="${PRECONV_FIRESTORE_SUBJECT_LINK_COLLECTION:-}" \
  --from-literal=SUBJECT_LINK_KEY_VERSION="${SUBJECT_LINK_KEY_VERSION:-v1}" \
  --from-literal=PRECONV_ICA_BASE_URL="${PRECONV_ICA_BASE_URL}" \
  --from-literal=PRECONV_ICA_TIMEOUT_SECONDS="${PRECONV_ICA_TIMEOUT_SECONDS:-15}" \
  --from-literal=PRECONV_TERMINOLOGY_BASE_URL="${PRECONV_TERMINOLOGY_BASE_URL:-}" \
  --from-literal=PRECONV_TERMINOLOGY_TIMEOUT_SECONDS="${PRECONV_TERMINOLOGY_TIMEOUT_SECONDS:-15}" \
  --from-literal=PRECONV_CODING_MODEL_BASE_URL="${PRECONV_CODING_MODEL_BASE_URL:-}" \
  --from-literal=PRECONV_CODING_MODEL_AUDIENCE="${PRECONV_CODING_MODEL_AUDIENCE:-}" \
  --from-literal=PRECONV_CODING_MODEL_ID="${PRECONV_CODING_MODEL_ID:-}" \
  --from-literal=PRECONV_CODING_MODEL_TIMEOUT_SECONDS="${PRECONV_CODING_MODEL_TIMEOUT_SECONDS:-30}" \
  --from-literal=PRECONV_PUBSUB_TOPIC_ID="${PRECONV_PUBSUB_TOPIC_ID:-}" \
  --from-literal=PRECONV_PUBSUB_SUBSCRIPTION_ID="${PRECONV_PUBSUB_SUBSCRIPTION_ID:-}" \
  --from-literal=PRECONV_GCS_PREFIX="${PRECONV_GCS_PREFIX:-}" \
  --from-literal=POSTGRES_SEARCH_TABLE="${POSTGRES_SEARCH_TABLE}" \
  --from-literal=PRECONV_DEFAULT_ISSUER_DID="${PRECONV_DEFAULT_ISSUER_DID:-did:web:globaldatacare.es:employee:preconversion}" \
  --from-literal=PRECONV_DEFAULT_AUDIENCE_DID="${PRECONV_DEFAULT_AUDIENCE_DID:-did:web:globaldatacare.es}" \
  --from-literal=PRECONV_DEFAULT_SUBJECT_DID_PREFIX="${PRECONV_DEFAULT_SUBJECT_DID_PREFIX:-did:web:globaldatacare.es}" \
  --from-literal=PRECONV_AUTH_MODE="${PRECONV_AUTH_MODE:-parse-only}" \
  --from-literal=DEMO_MODE="${DEMO_MODE:-false}" \
  --from-literal=EXCHANGE_ALLOW_INSECURE_ASSERTIONS="${EXCHANGE_ALLOW_INSECURE_ASSERTIONS:-false}" \
  --from-literal=EXCHANGE_OIDC_ISSUER="${EXCHANGE_OIDC_ISSUER}" \
  --from-literal=EXCHANGE_OIDC_AUDIENCE="${EXCHANGE_OIDC_AUDIENCE}" \
  --from-literal=EXCHANGE_OIDC_ALLOWED_ISSUERS="${EXCHANGE_OIDC_ALLOWED_ISSUERS:-${EXCHANGE_OIDC_ISSUER}}" \
  --from-literal=EXCHANGE_OIDC_ALLOWED_AUDIENCES="${EXCHANGE_OIDC_ALLOWED_AUDIENCES:-${EXCHANGE_OIDC_AUDIENCE}}" \
  --from-literal=SMART_GW_ALLOWED_ISSUERS="${SMART_GW_ALLOWED_ISSUERS}" \
  --from-literal=SMART_GW_EXPECTED_AUDIENCES="${SMART_GW_EXPECTED_AUDIENCES}" \
  --from-literal=SMART_GW_ISSUER_TENANT_BINDINGS="${SMART_GW_ISSUER_TENANT_BINDINGS}" \
  --from-literal=SMART_GW_DID_CACHE_TTL_SECONDS="${SMART_GW_DID_CACHE_TTL_SECONDS:-300}" \
  --from-literal=SMART_GW_HTTP_TIMEOUT_SECONDS="${SMART_GW_HTTP_TIMEOUT_SECONDS:-5}" \
  --from-literal=SMART_RESEARCH_AUTH_REQUIRED_IN_DEMO="${SMART_RESEARCH_AUTH_REQUIRED_IN_DEMO:-false}" \
  --from-literal=PRECONV_JOB_RESULT_TTL_SECONDS="${PRECONV_JOB_RESULT_TTL_SECONDS:-3600}" \
  --from-literal=ICLAIMS_APP_ID="${ICLAIMS_APP_ID}" \
  --from-literal=ICLAIMS_VERTICAL="${ICLAIMS_VERTICAL}" \
  --from-literal=ICLAIMS_LOCALE="${ICLAIMS_LOCALE}" \
  --from-literal=ICLAIMS_CODE_DOMAIN="${ICLAIMS_CODE_DOMAIN}" \
  --from-literal=ICLAIMS_INFERENCE_DOMAIN="${ICLAIMS_INFERENCE_DOMAIN}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "${K8S_NAMESPACE}" create secret generic "${SECRET_NAME}" \
  --from-literal=GCP_PROJECT_ID="${GCP_PROJECT_ID}" \
  --from-literal=GCP_REGION="${GCP_REGION}" \
  --from-literal=GCS_BUCKET_NAME="${GCS_BUCKET_NAME}" \
  --from-literal=SUBJECT_LINK_PROTECTION_KEY="${SUBJECT_LINK_PROTECTION_KEY}" \
  --from-literal=PRECONV_ICA_API_KEY="${PRECONV_ICA_API_KEY}" \
  --from-literal=PRECONV_TERMINOLOGY_TOKEN="${PRECONV_TERMINOLOGY_TOKEN:-}" \
  --from-literal=PRECONV_CODING_MODEL_TOKEN="${PRECONV_CODING_MODEL_TOKEN:-}" \
  --from-literal=EXCHANGE_SESSION_TOKEN_SECRET="${EXCHANGE_SESSION_TOKEN_SECRET}" \
  --from-literal=POSTGRES_DSN="${POSTGRES_DSN}" \
  --from-literal=POSTGRES_INSTANCE_CONNECTION_NAME="${POSTGRES_INSTANCE_CONNECTION_NAME}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f <(
  sed -e "s#namespace: preconversion#namespace: ${K8S_NAMESPACE}#g" \
      -e "s#your-gcp-project#${GCP_PROJECT_ID}#g" \
      -e "s#preconversion-api#${DEPLOY_API_NAME}#g" \
      -e "s#PRECONV_API_CMD#preconversion-api#g" \
      -e "s#^\([[:space:]]*image:\) .*#\1 ${IMAGE_REF:-$IMAGE_URI}#g" \
      -e "s#preconversion-sa#${SERVICE_ACCOUNT_NAME}#g" \
      -e "s#preconversion-config#${CONFIGMAP_NAME}#g" \
      -e "s#preconversion-secrets#${SECRET_NAME}#g" \
      -e "s#replicas: 2#replicas: ${API_REPLICAS}#g" \
      -e "s#maxUnavailable: 25%#maxUnavailable: ${API_MAX_UNAVAILABLE}#g" \
      -e "s#maxSurge: 25%#maxSurge: ${API_MAX_SURGE}#g" \
      "${REPO_DIR}/k8s/api-deployment.yaml"
)
kubectl apply -f <(
  sed -e "s#namespace: preconversion#namespace: ${K8S_NAMESPACE}#g" \
      -e "s#your-gcp-project#${GCP_PROJECT_ID}#g" \
      -e "s#preconversion-worker#${DEPLOY_WORKER_NAME}#g" \
      -e "s#PRECONV_WORKER_CMD#preconversion-worker#g" \
      -e "s#^\([[:space:]]*image:\) .*#\1 ${IMAGE_REF:-$IMAGE_URI}#g" \
      -e "s#preconversion-sa#${SERVICE_ACCOUNT_NAME}#g" \
      -e "s#preconversion-config#${CONFIGMAP_NAME}#g" \
      -e "s#preconversion-secrets#${SECRET_NAME}#g" \
      -e "s#replicas: 2#replicas: ${WORKER_REPLICAS}#g" \
      -e "s#maxUnavailable: 25%#maxUnavailable: ${WORKER_MAX_UNAVAILABLE}#g" \
      -e "s#maxSurge: 25%#maxSurge: ${WORKER_MAX_SURGE}#g" \
      "${REPO_DIR}/k8s/worker-deployment.yaml"
)
kubectl apply -f <(
  sed -e "s#namespace: preconversion#namespace: ${K8S_NAMESPACE}#g" \
      -e "s#your-gcp-project#${GCP_PROJECT_ID}#g" \
      -e "s#preconversion-cleanup#${ICLAIMS_APP_ID}-cleanup#g" \
      -e "s#PRECONV_CLEANUP_CMD#preconversion-cleanup#g" \
      -e "s#^\([[:space:]]*image:\) .*#\1 ${IMAGE_REF:-$IMAGE_URI}#g" \
      -e "s#SCHEDULE_PLACEHOLDER#${CLEANUP_SCHEDULE_ESCAPED}#g" \
      -e "s#preconversion-sa#${SERVICE_ACCOUNT_NAME}#g" \
      -e "s#preconversion-config#${CONFIGMAP_NAME}#g" \
      -e "s#preconversion-secrets#${SECRET_NAME}#g" \
      "${REPO_DIR}/k8s/cleanup-cronjob.yaml"
)
kubectl apply -f <(
  sed -e "s#namespace: preconversion#namespace: ${K8S_NAMESPACE}#g" \
      -e "s#preconversion-api#${SERVICE_NAME}#g" \
      "${REPO_DIR}/k8s/service.yaml"
)
kubectl apply -f <(
  sed -e "s#namespace: preconversion#namespace: ${K8S_NAMESPACE}#g" \
      -e "s#preconversion-api#${DEPLOY_API_NAME}#g" \
      -e "s#minReplicas: 2#minReplicas: ${HPA_MIN_REPLICAS}#g" \
      -e "s#maxReplicas: 10#maxReplicas: ${HPA_MAX_REPLICAS}#g" \
      "${REPO_DIR}/k8s/hpa-api.yaml"
)

if [[ "${APPLY_INGRESS:-true}" == "true" ]]; then
  if [[ -n "${MANAGED_CERT_NAME}" ]]; then
    kubectl apply -f <(
      sed -e "s#namespace: preconversion#namespace: ${K8S_NAMESPACE}#g" \
          -e "s#preconversion-cert#${MANAGED_CERT_NAME}#g" \
          -e "s#preconversion.example.globaldatacare.es#${INGRESS_HOST}#g" \
          "${REPO_DIR}/k8s/managed-certificate.yaml"
    )
  fi
  render_ingress_manifest | kubectl apply -f -
fi

kubectl -n "${K8S_NAMESPACE}" set image deployment/"${DEPLOY_API_NAME}" api="${IMAGE_REF}"
kubectl -n "${K8S_NAMESPACE}" set image deployment/"${DEPLOY_WORKER_NAME}" worker="${IMAGE_REF}"
kubectl -n "${K8S_NAMESPACE}" rollout restart deployment/"${DEPLOY_API_NAME}"
kubectl -n "${K8S_NAMESPACE}" rollout restart deployment/"${DEPLOY_WORKER_NAME}"

kubectl -n "${K8S_NAMESPACE}" rollout status deployment/"${DEPLOY_API_NAME}" --timeout=300s
kubectl -n "${K8S_NAMESPACE}" rollout status deployment/"${DEPLOY_WORKER_NAME}" --timeout=300s

echo
echo "Deployment finished."
echo "Deployed image ref: ${IMAGE_REF}"
kubectl -n "${K8S_NAMESPACE}" get pods -o wide
kubectl -n "${K8S_NAMESPACE}" get svc
