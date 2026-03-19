# 04 - Envío al gateway

## Precondiciones

- Ya probaste `--dry-run` con el mismo fichero y configuración.
- Tienes `auth token` válido (`Bearer`).
- Conoces `gateway-base-url`.

## Envío (ejemplo)

```bash
export AUTH_TOKEN="<bearer-token>"

PYTHONPATH=src python3 -m adapter_ingestion \
  --manufacturer qvet \
  --input "/ruta/export/listados mes de enero Qvet.xlsx" \
  --issuer-did "did:web:<example>.globaldatacare.es:employee:<email>:<rol>" \
  --audience-did "did:web:<clinica>.globaldatacare.es" \
  --species-catalog-file "./configs/clinic-acme.species.catalog.json" \
  --species-local-map-file "./configs/clinic-acme.species.map.json" \
  --schema-config-file "./configs/clinic-acme.qvet.schema.json" \
  --gateway-base-url "https://gateway.midominio.com" \
  --resource-route-prefix "/v1" \
  --auth-token "$AUTH_TOKEN" \
  --output-dir ./artifacts/qvet \
  --send
```

## ¿De dónde sale `AUTH_TOKEN`?

Actualmente el CLI no hace login interactivo.

Opciones típicas:

1. Token emitido por tu backend/IdP corporativo (recomendado en producción).
2. Google ID token (solo si tu gateway está configurado para validarlo).

Ejemplo CLI con Google (audience = client ID esperado por gateway):

```bash
gcloud auth login
export AUTH_TOKEN="$(gcloud auth print-identity-token --audiences="<GOOGLE_OAUTH_CLIENT_ID>")"
```

Notas:

- El token expira (normalmente ~1 hora).
- Si el gateway no acepta ese `aud`, devolverá 401/403.

## Sobre rutas con segmentos opcionales (`tenant/jurisdiction/sector`)

En este proyecto ya no son obligatorios para el flujo principal con dominio DID propio.

- Flujo recomendado: usar `--resource-route-prefix` (por ejemplo `/v1`).
- Si pasas `--tenant-id`, `--jurisdiction` y `--sector`, se usa esa forma de ruta.

## Qué envía

- Lote `Composition` a `.../Composition/_batch`

## Resultado esperado en consola

- Estado HTTP por cada POST.
- `location` si el gateway la devuelve.

## Recomendaciones de operación

- Ejecutar por lotes pequeños al iniciar una nueva clínica.
- Registrar fecha/hora, archivo fuente y `summary.json` de cada carga.
- Si hay error HTTP, conservar artefactos para reintento sin reprocesar origen.
