# 09 - Storage And Job Queue Adapters

Goal: decouple the pre-conversion API from the persistence and queue technologies.

## 1) Python ports

Defined in `src/adapter_ingestion/runtime/ports.py`:

- `ConfigStore`: persist and load configuration documents
- `JobStore`: persist and load job state
- `JobQueue`: enqueue and dequeue job identifiers

The domain logic depends only on these ports.

## 2) Supported configuration key

`ConfigKey` in `runtime/models.py` uses:

- `alternate_name`
- `manufacturer`
- `manufacturer_version`
- `country`
- `facility_id`

This supports franchise-style organizations with multiple locations.

## 3) Resolution fallback

`runtime/resolution.py` resolves configuration from most specific to most generic:

1. version + country + facility
2. version + country
3. version + facility
4. organization version
5. default version + country + facility
6. default version + country
7. default version + facility
8. default version organization

## 4) Included implementations

Under `runtime/adapters/`:

- `InMemoryConfigStore`, `InMemoryJobStore`, `InMemoryJobQueue`
- `FileSystemConfigStore`, `FileSystemJobStore`, `FileSystemJobQueue`
- `FirestoreConfigStore`, `FirestoreJobStore`
- `PubSubJobQueue`
- `InMemoryBlobStore`, `FileSystemBlobStore`, `GCSBlobStore`

`FileSystem*` is useful for local or persistent staging environments.

For GCP deployments, naming can be derived from `NODE_ENV`:

- `development`, `dev`, `demo`, `test`, `local` -> `dev`
- `staging` -> `staging`
- `production`, `prod` -> `prod`

Those profiles combine with `PRECONV_SECTOR_SCOPE` using `-`.

## 5) Control-plane service

`PreconversionControlPlane` in `runtime/control_plane.py` implements:

- `upsert_config(...)`
- `resolve_config(...)`
- `submit_job(...)`
- `claim_next_job(...)`
- `mark_job_succeeded(...)`
- `mark_job_failed(...)`

This is the reusable domain service behind any HTTP API.

## 6) Production path on GCP and Kubernetes

A single API can be deployed with production-grade adapters such as:

- `ConfigStore`: Firestore
- `JobStore`: Firestore or managed SQL
- `JobQueue`: Cloud Tasks, Pub/Sub, or Redis

Business logic remains unchanged. Only the adapters are replaced.

## 7) Current status

Implemented:

- in-memory
- filesystem
- Firestore
- Pub/Sub
- GCS

Testing status:

- Standard automated tests cover `mem`, `fs`, and naming/config resolution.
- Real GCP integration tests live in `tests/test_runtime_gcp_integration.py` and `scripts/run-gcp-adapter-integration.sh`.
- Cloud Tasks push-mode support remains an evolutionary path.
