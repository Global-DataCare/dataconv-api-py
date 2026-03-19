# 09 - Adaptadores de Storage y Job Queue (agnóstico de base de datos)

Objetivo: desacoplar la API de pre-conversión de la tecnología de persistencia/cola.

## 1) Puertos definidos en Python

En `src/adapter_ingestion/runtime/ports.py`:

- `ConfigStore`: guardar/leer configuración por clave lógica.
- `JobStore`: guardar/leer estado de jobs.
- `JobQueue`: encolar/desencolar IDs de job.

La lógica de dominio usa solo estos puertos.

## 2) Clave de configuración soportada

`ConfigKey` (`runtime/models.py`) usa:

- `alternate_name`
- `manufacturer`
- `manufacturer_version`
- `country`
- `facility_id`

Esto permite franquicia (organization) con múltiples sedes/location (facilities).

## 3) Resolución con fallback

`runtime/resolution.py` aplica fallback (de más específico a más genérico):

1. versión + país + facility
2. versión + país
3. versión + facility
4. versión organización
5. default-version + país + facility
6. default-version + país
7. default-version + facility
8. default-version organización

## 4) Implementaciones incluidas

En `runtime/adapters/`:

- `InMemoryConfigStore`, `InMemoryJobStore`, `InMemoryJobQueue`
- `FileSystemConfigStore`, `FileSystemJobStore`, `FileSystemJobQueue`
- `FirestoreConfigStore`, `FirestoreJobStore`
- `PubSubJobQueue`
- `InMemoryBlobStore`, `FileSystemBlobStore`, `GCSBlobStore`

`FileSystem*` sirve para entorno local/staging persistente.

En despliegues GCP, el runtime puede derivar automáticamente nombres por entorno a partir de `NODE_ENV`:

- `development`, `dev`, `demo`, `test`, `local` -> perfil `dev`
- `staging` -> perfil `staging`
- `production` / `prod` -> perfil `prod`

Y los combina con `PRECONV_SECTOR_SCOPE` usando `-`:

- `{profile}-preconvert-{sector}-configs`
- `{profile}-preconvert-{sector}-jobs`
- `{profile}-preconvert-{sector}-jobs-worker`
- `{profile}-preconvert-{sector}` para artefactos GCS

Siempre puedes sobrescribir esos nombres con variables explícitas (`PRECONV_FIRESTORE_*`, `PRECONV_PUBSUB_*`, `PRECONV_GCS_PREFIX`).

## 5) Servicio de control-plane

`PreconversionControlPlane` (`runtime/control_plane.py`) implementa:

- `upsert_config(...)`
- `resolve_config(...)`
- `submit_job(...)`
- `claim_next_job(...)`
- `mark_job_succeeded(...)`
- `mark_job_failed(...)`

Este servicio es el núcleo reusable para una API HTTP (FastAPI, Flask, etc.).

## 6) Camino a producción (GCP/Kubernetes)

La misma API puede desplegarse en Kubernetes con adapters productivos:

- `ConfigStore`: Firestore
- `JobStore`: Firestore o SQL administrado
- `JobQueue`: Cloud Tasks / PubSub / Redis

La lógica de negocio no cambia; solo se reemplazan adapters.

## 7) Estado actual

- Ya implementado: in-memory + filesystem + Firestore + Pub/Sub + GCS.
- Tests automáticos normales: cubren `mem`, `fs` y resolución de naming/config.
- Tests de integración GCP real: `tests/test_runtime_gcp_integration.py` y `scripts/run-gcp-adapter-integration.sh` (solo se ejecutan si defines `RUN_GCP_INTEGRATION=1` y tienes credenciales GCP válidas).
- En evolución: variante push con Cloud Tasks (si se prefiere callback worker).
