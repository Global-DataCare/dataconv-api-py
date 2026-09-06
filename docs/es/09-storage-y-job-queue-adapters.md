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

## 6) Revisión de research y promoción al índice

Los jobs nuevos del sector explícito `onehealth-research` conservan una referencia FHIR estable a
`ResearchStudy` desde upload hasta la revisión. Poll y patch deben repetirla,
y el ResearchSubject promovido la publica únicamente mediante la claim
estándar `ResearchSubject.study`. `study` sirve para correlación y búsqueda, no
es una regla local de autorización; Consent y SMART siguen perteneciendo al
GW. Los jobs históricos sin esta referencia todavía se pueden consultar, pero
no promover mediante el patch limitado al estudio.
Los demás sectores conservan el contrato existente de upload y patch sin
exigir este campo exclusivo de research.

El ciclo persistente es:

```text
GCS -> Firestore draft -> human review -> PostgreSQL search index
```

1. GCS guarda el archivo de origen y los artefactos generados por el job.
2. DataConv genera recursos procesados de forma FHIR-like con flat claims
   canónicas.
3. Firestore guarda esos recursos como borradores `userSelected=true` y las
   relaciones necesarias para revisarlos.
4. Una persona revisa los códigos terminológicos inferidos y confirma o rechaza
   el borrador. La confirmación cambia `userSelected` a `false`.
5. El mismo recurso procesado y confirmado se copia a PostgreSQL; no es una
   segunda versión extraída o transformada.
6. PostgreSQL guarda `claims`, `search_fields` normalizados y el `resource`
   completo. Las consultas filtran `search_fields` y devuelven `resource`.

La copia completa en ambas bases evita releer Firestore por cada resultado de
búsqueda, a cambio de duplicación. Cualquier rediseño debe definir primero una
única fuente autoritativa para recursos promovidos y su reconciliación.

La inferencia de texto a código solo puede producir propuestas. El servicio de
terminología devuelve todos los candidatos gobernados y el modelo añade un
porcentaje de recomendación y evidencia sin eliminar alternativas. Esos datos
viven en `meta.codingProposals[]`, fuera de las flat claims autoritativas. La
decisión human-reviewed escribe únicamente `<Resource>.code` y el
`<Resource>.code-display` en inglés. La revisión envía candidatos aceptados y
rechazados, junto con el motivo opcional, a `/v1/coding/feedback`; esto crea
datos de evaluación o entrenamiento, no aprendizaje online automático. El
worker usa `NoopCodingAssistant` solo si falta
`PRECONV_TERMINOLOGY_BASE_URL` o `PRECONV_CODING_MODEL_BASE_URL`.

Un runtime de modelo reutilizable puede exponer contratos independientes para
intents de aplicación, resolución de dudas y codificación clínica. El endpoint de
intents existente no constituye por sí mismo un servicio terminológico. Para
codificar, DataConv necesita restringir la consulta a los sistemas y value sets
aplicables mediante:

- [`ValueSet/$expand?filter=`](https://hl7.org/fhir/R4/valueset-operation-expand.html)
  para obtener candidatos filtrados por texto;
- [`ValueSet/$validate-code`](https://hl7.org/fhir/R4/valueset-operation-validate-code.html)
  para validar que el código elegido pertenece al value set gobernado;
- [`ConceptMap/$translate`](https://hl7.org/fhir/R4/conceptmap-operation-translate.html)
  para traducir un código ya identificado mediante un ConceptMap explícito si
  se necesita otro sistema de codificación.

El modelo puede normalizar el texto libre y ordenar los candidatos devueltos
por el servicio terminológico. No puede inventar el código, elegir en silencio
el sistema ni saltarse la revisión humana. Los textos de condition,
observation/test y procedure deben resolverse con los value sets y restricciones
de perfil o jurisdicción correspondientes.

## 7) Camino a producción (GCP/Kubernetes)

La misma API puede desplegarse en Kubernetes con adapters productivos:

- `ConfigStore`: Firestore
- `JobStore`: Firestore o SQL administrado
- `JobQueue`: Cloud Tasks / PubSub / Redis

La lógica de negocio no cambia; solo se reemplazan adapters.

## 8) Estado actual

- Ya implementado: in-memory + filesystem + Firestore + Pub/Sub + GCS +
  repositorio de búsqueda PostgreSQL.
- Tests automáticos normales: cubren `mem`, `fs` y resolución de naming/config.
- Tests de integración GCP real: `tests/test_runtime_gcp_integration.py` y `scripts/run-gcp-adapter-integration.sh` (solo se ejecutan si defines `RUN_GCP_INTEGRATION=1` y tienes credenciales GCP válidas).
- `tests/test_manager_conversion_patch.py` prueba la promoción tras revisión y
  `tests/test_runtime_postgres_search_integration.py` prueba la persistencia y
  devolución desde PostgreSQL.
- La codificación remota y el feedback de revisión se activan solo cuando se
  configuran sus URLs; en caso contrario el worker usa `NoopCodingAssistant`.
- En evolución: variante push con Cloud Tasks (si se prefiere callback worker).
