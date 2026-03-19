# 11 - Pipeline de release (staging -> production por digest)

Objetivo: construir una vez, validar en staging y promover exactamente la misma imagen a production.

## 1) Preparar entornos

```bash
cp .env.deploy.staging.example .env.deploy.staging
cp .env.deploy.production.example .env.deploy.production
```

Configurar `DOCKER_IMAGE_TAG` distinto por entorno, por ejemplo:

- staging: `staging-latest`
- production: `prod-latest`

Los nombres de colecciones/topics/prefix también pueden resolverse automáticamente por `NODE_ENV`:

- `development`, `dev`, `test`, `demo` y `local` se normalizan a perfil `dev`
- `staging` se mantiene como `staging`
- `production` se normaliza a `prod`

Además se combinan con `PRECONV_SECTOR_SCOPE` y el patrón:

- `{profile}-preconvert-{sector}-configs`
- `{profile}-preconvert-{sector}-jobs`
- `{profile}-preconvert-{sector}-jobs-worker`
- `{profile}-preconvert-{sector}` para `GCS prefix`

Si prefieres nombres exactos, sigue definiéndolos explícitamente en cada `.env.deploy.*`.

Y fija `ICLAIMS_APP_ID` por vertical/idioma:

- veterinaria: `vet-claims-api`
- salud general: `health-claims-api`

Mantén `ICLAIMS_CODE_DOMAIN=none` e `ICLAIMS_INFERENCE_DOMAIN=none` hasta definir ontologías/inferencia productivas.

## 2) Build + deploy en staging

```bash
./scripts/deploy-gke.sh staging
```

Este paso:

1. build local de imagen.
2. push al registry.
3. despliegue en GKE staging.

## 3) Promover imagen validada (sin recompilar)

```bash
./scripts/promote-image.sh staging production
```

El script:

- resuelve el `sha256` de la imagen usada en staging.
- crea tag de production para ese mismo digest.
- muestra el `image@sha256:...` inmutable.

## 4) Deploy en production con la misma imagen

Usar el digest mostrado en el paso anterior:

```bash
PRECONV_IMAGE_REF="europe-west1-docker.pkg.dev/.../preconversion-api@sha256:..." \
PRECONV_SKIP_BUILD=true \
./scripts/deploy-gke.sh production
```

No se recompila nada en production.

## 5) Verificación rápida

```bash
kubectl -n <namespace-prod> get deploy preconversion-api -o jsonpath='{.spec.template.spec.containers[0].image}'
kubectl -n <namespace-prod> get deploy preconversion-worker -o jsonpath='{.spec.template.spec.containers[0].image}'
```

Ambos deben quedar fijados al mismo `@sha256`.
