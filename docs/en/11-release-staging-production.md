# 11 - Release Pipeline: Staging To Production By Digest

Goal: build once, validate in staging, and promote the exact same image to production.

## 1) Prepare environments

```bash
cp .env.deploy.staging.example .env.deploy.staging
cp .env.deploy.production.example .env.deploy.production
```

Use different `DOCKER_IMAGE_TAG` values per environment, for example:

- staging: `staging-latest`
- production: `prod-latest`

Collection, topic, and prefix names can still be derived automatically from `NODE_ENV`. If you prefer exact names, define them explicitly in each `.env.deploy.*` file.

Set `ICLAIMS_APP_ID` per vertical and locale, for example:

- veterinary: `vet-claims-api`
- general health: `health-claims-api`

Keep `ICLAIMS_CODE_DOMAIN=none` and `ICLAIMS_INFERENCE_DOMAIN=none` until production-grade ontologies and inference are defined.

## 2) Build and deploy to staging

```bash
./scripts/deploy-gke.sh staging
```

This step:

1. builds the image locally
2. pushes it to the registry
3. deploys it to the staging cluster

## 3) Promote the validated image without rebuilding

```bash
./scripts/promote-image.sh staging production
```

The script:

- resolves the `sha256` digest used in staging
- creates the production tag for the same digest
- prints the immutable `image@sha256:...` reference

## 4) Deploy the same digest to production

```bash
PRECONV_IMAGE_REF="europe-west1-docker.pkg.dev/.../preconversion-api@sha256:..." \
PRECONV_SKIP_BUILD=true \
./scripts/deploy-gke.sh production
```

No production rebuild happens in this flow.

## 5) Quick verification

```bash
kubectl -n <namespace-prod> get deploy preconversion-api -o jsonpath='{.spec.template.spec.containers[0].image}'
kubectl -n <namespace-prod> get deploy preconversion-worker -o jsonpath='{.spec.template.spec.containers[0].image}'
```

Both deployments must point to the same immutable digest.
