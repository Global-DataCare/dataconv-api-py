# 13 - Bootstrap GCP para `api-convert-onehealth`

Objetivo: dejar un proyecto GCP propio para `preconvert`, sin mezclar datos ni buckets con `globaldatacare-*`, pero reutilizando un patrón operativo sencillo.

## 1) Decisión actual

- Proyecto GCP único: `api-convert-onehealth`
- Caso de uso: research / conversión sin datos personales
- Un cluster GKE regional para el entorno compartido inicial
- Separación funcional dentro del mismo proyecto:
  - namespaces Kubernetes: `shared`, `animal`, `health`
  - colecciones Firestore: `dev-preconvert-animal-configs`, `dev-preconvert-health-configs`, etc.
  - topics/subscriptions Pub/Sub y prefijos GCS siguiendo el mismo patrón

El naming de recursos aplicados por este servicio ya está normalizado como:

- `{profile}-preconvert-{sector}-configs`
- `{profile}-preconvert-{sector}-jobs`
- `{profile}-preconvert-{sector}-jobs-worker`
- `{profile}-preconvert-{sector}`

Donde:

- `profile` = `dev`, `staging`, `prod`
- `sector` = `animal`, `health`

## 2) Topología recomendada

- Región GKE: `europe-southwest1`
- Tipo de cluster: `Standard regional`
- Nodos por zona: `1`
- Nodos totales: `3` en la región
- Tipo de máquina inicial: `e2-medium`

Eso replica el patrón ya usado en `google-cloud-team-bootstrap`: cluster regional con una réplica de nodo por zona, para tener alta disponibilidad básica sin sobredimensionar costes.

## 3) IAM del equipo

Separación recomendada:

- `manager`: responsable técnico/propietario del proyecto
- `operators`: equipo operativo que despliega y revisa logs

Operadores definidos ahora:

- `dverma@connecthealth.info`
- `bcolmenares@connecthealth.info`

En el bootstrap de este repo:

- `manager` recibe roles de administración de cluster, Artifact Registry, Firestore, Pub/Sub y GCS
- `operators` reciben roles operativos de despliegue y observabilidad

El email del `manager` se deja como variable para no hardcodearlo en el repo.

Valor recomendado ahora:

- `fernandolatorre@connecthealth.info`

## 4) Script de bootstrap

Se añadió:

- `scripts/bootstrap-gcp-project.sh`

Y una plantilla de variables:

- `examples/gcp/api-convert-onehealth.bootstrap.env.example`
- `private-gcp-bootstrap.config.example`

Flujo:

```bash
cd /Users/fernando/GITS/gdc-workspace/adapter-ingestion-py

cp private-gcp-bootstrap.config.example private-gcp-bootstrap.config
$EDITOR private-gcp-bootstrap.config
source private-gcp-bootstrap.config

bash scripts/bootstrap-gcp-project.sh
```

`private-gcp-bootstrap.config` está en `.gitignore`, así que los emails, billing account y demás valores sensibles no se quedan versionados.

El script crea o asegura:

- proyecto GCP
- enlace a billing
- APIs base (`GKE`, `Artifact Registry`, `Firestore`, `Pub/Sub`, `GCS`, etc.)
- IAM para `manager` y `operators`
- repositorio Docker
- bucket GCS
- cluster GKE regional
- namespaces `shared`, `animal`, `health`
- base Firestore opcional si defines `FIRESTORE_LOCATION`

## 5) Relación con el deploy del servicio

Después del bootstrap, cada despliegue del servicio decide el namespace y el sector.

Ejemplo `animal`:

```bash
cp .env.deploy.staging.example .env.deploy.staging
```

Valores relevantes:

```bash
K8S_NAMESPACE=animal
PRECONV_SECTOR_SCOPE=animal
NODE_ENV=staging
GCP_PROJECT_ID=api-convert-onehealth
K8S_CLUSTER=onehealth-staging
```

Ejemplo `health`:

```bash
K8S_NAMESPACE=health
PRECONV_SECTOR_SCOPE=health
NODE_ENV=staging
GCP_PROJECT_ID=api-convert-onehealth
K8S_CLUSTER=onehealth-staging
```

Con eso, ambos despliegues comparten proyecto y cluster, pero quedan separados por namespace y por naming de recursos backend.

## 6) Recomendación de alcance

Para esta fase de research, un único proyecto `api-convert-onehealth` es razonable.

Si más adelante aparece producción real o requisitos regulatorios distintos, entonces sí conviene separar al menos:

- `api-convert-onehealth-staging`
- `api-convert-onehealth-prod`

Pero no hace falta abrir ese frente todavía.
