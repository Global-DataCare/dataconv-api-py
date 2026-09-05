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

## 6) Research review and searchable promotion

The persistent research lifecycle is:

```text
GCS -> Firestore draft -> human review -> PostgreSQL search index
```

1. GCS stores the uploaded source and generated job artifacts.
2. DataConv produces processed FHIR-like resources with canonical flat claims.
3. Firestore stores those resources as `userSelected=true` drafts and keeps
   the links required for review.
4. A human reviews inferred terminology codes and confirms or rejects the
   draft. Confirmation changes `userSelected` to `false`.
5. The same processed confirmed resource is copied to PostgreSQL. It is not a
   second extracted or transformed version.
6. PostgreSQL stores `claims`, normalized `search_fields`, and the complete
   `resource`. Queries filter `search_fields` and return `resource`.

Keeping the complete resource in both Firestore and PostgreSQL avoids a
Firestore hydration read for every search result, at the cost of duplication.
Any later redesign must define one authoritative promoted-resource store and a
reconciliation rule before removing either copy.

Text-to-code inference is proposal-only. The AI boundary may return a code,
system, display, confidence, and evidence, but only a human-reviewed decision
may promote data. Accepted and rejected proposals can feed a governed,
de-identified, human-reviewed evaluation or training dataset; model output is
never ground truth by itself. The deployed worker currently constructs
`NoopCodingAssistant`, so no remote AI service is integrated into this runtime.

A reusable model runtime may expose separate contracts for application intents,
question answering, and clinical coding. Existing intent classification does
not by itself implement terminology resolution. The coding path requires a
terminology service constrained to the applicable systems and value sets:

- [`ValueSet/$expand?filter=`](https://hl7.org/fhir/R4/valueset-operation-expand.html)
  returns text-filtered candidates for a selected value set;
- [`ValueSet/$validate-code`](https://hl7.org/fhir/R4/valueset-operation-validate-code.html)
  verifies that the selected code belongs to the governed value set;
- [`ConceptMap/$translate`](https://hl7.org/fhir/R4/conceptmap-operation-translate.html)
  translates an already identified code through an explicit ConceptMap when
  another coding system is required.

The model may normalize free text and rank terminology-service candidates. It
must not fabricate a code, silently choose a coding system, or bypass human
review. Condition, observation/test, and procedure text must be resolved under
their own configured value-set and jurisdiction/profile constraints.

## 7) Production path on GCP and Kubernetes

A single API can be deployed with production-grade adapters such as:

- `ConfigStore`: Firestore
- `JobStore`: Firestore or managed SQL
- `JobQueue`: Cloud Tasks, Pub/Sub, or Redis

Business logic remains unchanged. Only the adapters are replaced.

## 8) Current status

Implemented:

- in-memory
- filesystem
- Firestore
- Pub/Sub
- GCS
- PostgreSQL search repository

Testing status:

- Standard automated tests cover `mem`, `fs`, and naming/config resolution.
- Real GCP integration tests live in `tests/test_runtime_gcp_integration.py` and `scripts/run-gcp-adapter-integration.sh`.
- The human-review promotion contract is covered by
  `tests/test_manager_conversion_patch.py`; PostgreSQL storage and return
  behavior is covered by `tests/test_runtime_postgres_search_integration.py`.
- Remote coding-assistant integration and durable review-decision capture are
  pending; the service worker uses `NoopCodingAssistant`.
- Cloud Tasks push-mode support remains an evolutionary path.
