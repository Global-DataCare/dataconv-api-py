# 13 - GCP Bootstrap For `api-convert-onehealth`

Goal: provision a dedicated GCP project for `preconvert` without mixing data or buckets with `globaldatacare-*`, while keeping the operating model simple.

## 1) Current decision

- Single GCP project: `api-convert-onehealth`
- Use case: research and conversion without personal data
- One regional GKE cluster for the initial shared environment
- Functional separation inside the same project:
  - Kubernetes namespaces: `shared`, `animal`, `health`
  - Firestore collections such as `dev-preconvert-animal-configs`
  - Pub/Sub topics/subscriptions and GCS prefixes following the same pattern

Resource naming follows:

- `{profile}-preconvert-{sector}-configs`
- `{profile}-preconvert-{sector}-jobs`
- `{profile}-preconvert-{sector}-jobs-worker`
- `{profile}-preconvert-{sector}`

Where `profile` is one of `dev`, `staging`, or `prod`, and `sector` is `animal` or `health`.

## 2) Recommended topology

- Region: `europe-southwest1`
- Cluster type: regional standard cluster
- Nodes per zone: `1`
- Total nodes across the region: `3`
- Initial machine type: `e2-medium`

This mirrors the already used bootstrap pattern: one node per zone for basic high availability without oversizing costs.

## 3) Team IAM model

Recommended separation:

- `manager`: technical owner of the project
- `operators`: team members who deploy and inspect logs

Current operators:

- `dverma@connecthealth.info`
- `bcolmenares@connecthealth.info`

Recommended manager value:

- `fernandolatorre@connecthealth.info`

The bootstrap grants admin capabilities to the manager and deployment plus observability roles to operators.

## 4) Bootstrap script

Files added for this flow:

- `scripts/bootstrap-gcp-project.sh`
- `examples/gcp/api-convert-onehealth.bootstrap.env.example`
- `private-gcp-bootstrap.config.example`

Typical flow:

```bash
cd /Users/fernando/GITS/gdc-workspace/dataconv-api-py

cp private-gcp-bootstrap.config.example private-gcp-bootstrap.config
$EDITOR private-gcp-bootstrap.config
source private-gcp-bootstrap.config

bash scripts/bootstrap-gcp-project.sh
```

`private-gcp-bootstrap.config` is gitignored, so billing accounts and email addresses stay outside version control.

The script creates or guarantees:

- GCP project
- billing linkage
- required APIs
- IAM bindings for manager and operators
- Docker repository
- GCS bucket
- regional GKE cluster
- namespaces `shared`, `animal`, `health`
- optional Firestore database if `FIRESTORE_LOCATION` is defined

## 5) Relationship to service deployment

After bootstrap, each deployment selects namespace and sector.

Animal example:

```bash
K8S_NAMESPACE=animal
PRECONV_SECTOR_SCOPE=animal
NODE_ENV=staging
GCP_PROJECT_ID=api-convert-onehealth
K8S_CLUSTER=onehealth-staging
```

Health example:

```bash
K8S_NAMESPACE=health
PRECONV_SECTOR_SCOPE=health
NODE_ENV=staging
GCP_PROJECT_ID=api-convert-onehealth
K8S_CLUSTER=onehealth-staging
```

Both deployments share the same project and cluster but remain separated by namespace and by backend resource naming.

## 6) Scope recommendation

For the current research phase, one project `api-convert-onehealth` is a reasonable compromise.

If real production or stricter regulatory requirements appear later, split at least into:

- `api-convert-onehealth-staging`
- `api-convert-onehealth-prod`

That separation is not necessary yet.
