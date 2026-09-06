# 10 - Quick GKE Deployment

Goal: deploy the pre-conversion API and workers quickly for trial production environments.

If the GCP project, bucket, or base cluster does not exist yet, start with [13 - GCP bootstrap for One Health](13-gcp-bootstrap-onehealth.md).

## 1) Minimum recommended architecture

- `${ICLAIMS_APP_ID}` API deployment for HTTP endpoints
- `${ICLAIMS_APP_ID}-worker` deployment for queue processing
- `${ICLAIMS_APP_ID}-cleanup` CronJob for expired job cleanup
- Firestore for configuration and job state
- Pub/Sub for the worker queue
- GCS for input, output, and generated artifacts

## 2) Prepare deployment variables

```bash
cp .env.deploy.production.example .env.deploy.production
```

Fill at least:

- `GCP_PROJECT_ID`
- `GCP_REGION`
- `K8S_CLUSTER`
- `K8S_NAMESPACE`
- `PRECONV_GCP_SERVICE_ACCOUNT`
- `PRECONV_INGRESS_HOST`
- `PRECONV_INGRESS_STATIC_IP_NAME`
- `PRECONV_MANAGED_CERT_NAME`, `PRECONV_PRE_SHARED_CERT_NAME`, or `PRECONV_TLS_SECRET_NAME`
- `PRECONV_DISABLE_HTTP`
- `GCS_BUCKET_NAME`
- `ICLAIMS_APP_ID`
- `ICLAIMS_VERTICAL`, `ICLAIMS_LOCALE`
- `ICLAIMS_CODE_DOMAIN`, `ICLAIMS_INFERENCE_DOMAIN`
- `PRECONV_JOB_RESULT_TTL_SECONDS`
- `PRECONV_CLEANUP_SCHEDULE`
- `API_REPLICAS`, `WORKER_REPLICAS`
- HPA and rollout settings

Automatic naming uses `{profile}-preconvert-{dataspace}-{resource}`. Explicit `PRECONV_FIRESTORE_*`, `PRECONV_PUBSUB_*`, and `PRECONV_GCS_PREFIX` values override the derived names.

Logging:

- API, worker, and cleanup emit structured JSON events to stdout.
- On GKE, Cloud Logging collects fields such as `tenantId`, `softwareId`, `thid`, and `jobId`.

## 2.b) Quick local check before GKE

```bash
pip install -e ".[prod]"
cp .env.local.example .env.local
preconversion-api
```

In another terminal:

```bash
preconversion-worker
```

Technical health endpoint:

- `GET /healthz` is for liveness, readiness, and platform monitoring only.

## 3) Build and deploy

```bash
./scripts/deploy-gke.sh production
```

The script:

1. Builds and pushes the Docker image
2. Creates or updates `ConfigMap` and `Secret`
3. Applies Kubernetes manifests
4. Updates the API and worker image references
5. Waits for rollout completion

Release-related variables:

- `PRECONV_IMAGE_REF`
- `PRECONV_SKIP_BUILD=true`
- `PRECONV_INGRESS_STATIC_IP_NAME`
- exactly one TLS mode among `PRECONV_MANAGED_CERT_NAME`, `PRECONV_PRE_SHARED_CERT_NAME`, or `PRECONV_TLS_SECRET_NAME`
- `PRECONV_TERMINOLOGY_INGRESS_ENABLED=true` to add `/v1/terminology` to the
  same Ingress, together with `PRECONV_TERMINOLOGY_INGRESS_SERVICE_NAME` and
  `PRECONV_TERMINOLOGY_INGRESS_SERVICE_PORT`

The terminology target must be a Service in `K8S_NAMESPACE`; the configured
port is its Kubernetes Service port. The path is not rewritten. The more
specific terminology prefix is emitted before the `/` catch-all, which remains
bound to the DataConv API. The option defaults to `false` and does not deploy
the terminology workload itself.

Recommended profiles:

- `staging`: static IP plus pre-shared certificate is simple and predictable
- `production`: managed certificate plus fully qualified domain name

## 4) Client-facing API contract

The public DIDComm contract and end-to-end examples are documented in [08 - Multi-tenant API configuration](08-multi-tenant-api-configuration.md).

Public Swagger only documents business endpoints such as `_create`, `_create-response`, `_upload`, and `_upload-response`.

## 5) Note on Cloud Tasks

This repository currently implements Pub/Sub pull workers on Kubernetes. If you later want Cloud Tasks push delivery, add a worker callback endpoint and change the consumption model accordingly.
