# Kubernetes Manifests (GKE)

Archivos incluidos:

- `namespace.yaml`
- `serviceaccount.yaml`
- `configmap.yaml`
- `secret.template.yaml`
- `api-deployment.yaml`
- `worker-deployment.yaml`
- `cleanup-cronjob.yaml`
- `service.yaml`
- `hpa-api.yaml`
- `ingress.yaml`

Flujo recomendado:

1. Ajustar valores de `.env.deploy.production`.
2. Ejecutar `./scripts/deploy-gke.sh production`.
3. Revisar pods y logs en el namespace configurado.

Nota:

- El script de despliegue crea/actualiza `ConfigMap` y `Secret` dinámicamente.
- El script también genera el `Ingress` según `.env.deploy.*`, con `host` opcional y modo TLS por `ManagedCertificate`, `pre-shared cert` o `Secret`.
- De forma opt-in, el mismo `Ingress` puede enrutar `/v1/terminology` sin
  reescritura a otro Service del namespace mediante
  `PRECONV_TERMINOLOGY_INGRESS_ENABLED`,
  `PRECONV_TERMINOLOGY_INGRESS_SERVICE_NAME` y
  `PRECONV_TERMINOLOGY_INGRESS_SERVICE_PORT`; `/` permanece en DataConv.
- `ICLAIMS_APP_ID` define el nombre de API (`<app-id>`) y worker (`<app-id>-worker`).
- `ICLAIMS_APP_ID` también define el nombre del cron de limpieza (`<app-id>-cleanup`).
- `QUEUE_PROVIDER=pubsub` está diseñado para worker pull.
- `PRECONV_CLEANUP_SCHEDULE` controla la frecuencia del cleanup global de jobs expirados.
