# 10 - Despliegue rápido en GKE (producción de prueba)

Objetivo: tener la API de pre-conversión y workers funcionando rápido para pruebas con empresas de software.

Si todavía no existe el proyecto GCP, el bucket o el cluster base, usa primero:

- `docs/es/13-bootstrap-gcp-onehealth.md`

## 1) Arquitectura mínima recomendada

- `${ICLAIMS_APP_ID}` (Deployment API): expone endpoints HTTP.
- `${ICLAIMS_APP_ID}-worker` (Deployment worker): consume cola y procesa jobs.
- `${ICLAIMS_APP_ID}-cleanup` (CronJob): limpieza global de jobs expirados (todos los tenants).
- `Firestore`: configuración y estado de jobs.
- `Pub/Sub`: cola de jobs (pull worker).
- `GCS`: entrada/salida de ficheros y artefactos.

## 2) Preparar variables de despliegue

```bash
cp .env.deploy.production.example .env.deploy.production
```

Completar:

- `GCP_PROJECT_ID`
- `GCP_REGION`
- `K8S_CLUSTER`
- `K8S_NAMESPACE`
- `PRECONV_GCP_SERVICE_ACCOUNT` (Workload Identity)
- `PRECONV_INGRESS_HOST`
- `PRECONV_INGRESS_STATIC_IP_NAME` (recomendado para tener IP pública estable)
- `PRECONV_MANAGED_CERT_NAME` (modo dominio con TLS gestionado por Google)
- `PRECONV_PRE_SHARED_CERT_NAME` (modo IP o dominio con certificado autogestionado ya cargado en GCP)
- `PRECONV_TLS_SECRET_NAME` (alternativa: `Secret` TLS de Kubernetes)
- `PRECONV_DISABLE_HTTP` (`true` para forzar solo HTTPS cuando usas certificado autogestionado)
- `GCS_BUCKET_NAME`
- `ICLAIMS_APP_ID` (ejemplo: `vet-claims-api`)
- `ICLAIMS_VERTICAL`, `ICLAIMS_LOCALE`
- `ICLAIMS_CODE_DOMAIN`, `ICLAIMS_INFERENCE_DOMAIN` (opcional, dejar `none` por ahora)
- `PRECONV_JOB_RESULT_TTL_SECONDS` (retención de respuestas terminales)
- `PRECONV_CLEANUP_SCHEDULE` (frecuencia del CronJob, por defecto cada 15 min)
- `API_REPLICAS`, `WORKER_REPLICAS` (réplicas iniciales)
- `API_MAX_SURGE`, `API_MAX_UNAVAILABLE`
- `WORKER_MAX_SURGE`, `WORKER_MAX_UNAVAILABLE`
- `HPA_MIN_REPLICAS`, `HPA_MAX_REPLICAS`

Resolución automática por entorno:

- El patrón base es `{profile}-preconvert-{dataspace}-{resource}` con `-`.
- `profile` se normaliza a `dev`, `staging` o `prod`.
- `PRECONV_DATASPACE_ID` identifica el dataspace de este deployment (ej. `globaldatacare`, `procuredata`, `animal`). Se usa como slug en nombres de recursos GCP; si no se define, se deduce del vertical por defecto.
- Ejemplo para `NODE_ENV=staging` y `PRECONV_DATASPACE_ID=animal`:
  - `staging-preconvert-animal-configs`
  - `staging-preconvert-animal-jobs`
  - `staging-preconvert-animal-jobs-worker`
  - `staging-preconvert-animal`
- Ejemplo para `NODE_ENV=production` y `PRECONV_DATASPACE_ID=globaldatacare`:
  - `prod-preconvert-globaldatacare-configs`
  - `prod-preconvert-globaldatacare-jobs`
  - `prod-preconvert-globaldatacare-jobs-worker`
  - `prod-preconvert-globaldatacare`
- Si defines explícitamente `PRECONV_FIRESTORE_*`, `PRECONV_PUBSUB_*` o `PRECONV_GCS_PREFIX`, esos valores tienen prioridad.

Logging:

- API/worker/cleanup emiten eventos JSON estructurados a stdout.
- En GKE esos eventos se recogen en Cloud Logging con campos como `tenantId`, `softwareId`, `thid`, `jobId`.

## 2.b) Prueba local rápida (antes de subir a GKE)

```bash
pip install -e ".[prod]"
cp .env.local.example .env.local
preconversion-api
```

En otra terminal:

```bash
preconversion-worker
```

La API y el worker leen `.env` y `.env.local` automáticamente si existen.

Endpoint técnico de despliegue:

- `GET /healthz` se usa solo para liveness/readiness y monitorización de plataforma.
- `healthz` no forma parte del contrato funcional para integradores y no aparece en Swagger público.

## 3) Construir y desplegar

```bash
./scripts/deploy-gke.sh production
```

El script:

1. build + push de imagen Docker al Artifact Registry.
2. crea/actualiza `ConfigMap` y `Secret`.
3. aplica manifests Kubernetes.
4. actualiza imagen en API y worker.
5. espera `rollout` correcto.

Variables opcionales de release:

- `PRECONV_IMAGE_REF`: despliega una imagen concreta (ej. `image@sha256:...`).
- `PRECONV_SKIP_BUILD=true`: no compila imagen (requiere `PRECONV_IMAGE_REF`).
- El script inyecta la imagen final también en el `CronJob` de limpieza.
- Si defines `PRECONV_INGRESS_STATIC_IP_NAME`, el `Ingress` de GCE queda anclado a esa IP global reservada.
- Si defines `PRECONV_MANAGED_CERT_NAME`, el deploy crea un `ManagedCertificate` y anota el `Ingress` para emitir TLS automáticamente cuando el DNS ya resuelve a la IP del balanceador. Este modo requiere `PRECONV_INGRESS_HOST`.
- Si defines `PRECONV_PRE_SHARED_CERT_NAME`, el `Ingress` usa un certificado SSL de GCP cargado previamente y puede funcionar con `PRECONV_INGRESS_HOST` vacío para exponer la IP directa.
- Si defines `PRECONV_TLS_SECRET_NAME`, el `Ingress` publica TLS usando un `Secret` Kubernetes en vez de un certificado gestionado de GCP.
- El script valida que solo haya un modo TLS activo a la vez: `PRECONV_MANAGED_CERT_NAME`, `PRECONV_PRE_SHARED_CERT_NAME` o `PRECONV_TLS_SECRET_NAME`.
- Para clusters pequeños de `staging`, usa `API_REPLICAS=1`, `WORKER_REPLICAS=1`, `*_MAX_SURGE=0` y `*_MAX_UNAVAILABLE=100%` para evitar bloqueos de CPU durante el rollout.
- Si haces `source .env.deploy.*`, deja `PRECONV_CLEANUP_SCHEDULE` entre comillas, por ejemplo `"*/5 * * * *"`.

Perfiles recomendados:

- `staging`: IP estática + `PRECONV_PRE_SHARED_CERT_NAME` + `PRECONV_INGRESS_HOST=` + `PRECONV_DISABLE_HTTP=false` si quieres abrir también HTTP en entorno de pruebas.
- `production`: dominio + `PRECONV_MANAGED_CERT_NAME` + `PRECONV_INGRESS_HOST=<fqdn>`.

## 4) Contrato de cliente (uso API)

Los ejemplos de consumo del cliente (Linux/macOS y Windows), junto con el contrato DIDComm público, están en:

- `docs/es/08-api-config-multitenant.md`

El Swagger público documenta únicamente endpoints de negocio (`_create`, `_create-response`, `_upload`, `_upload-response`).

## 5) Nota sobre Cloud Tasks

En este repo se implementa `Pub/Sub` para worker pull en Kubernetes.
Si más adelante prefieres Cloud Tasks (push), hay que añadir endpoint worker-callback y cambiar modelo de consumo.
