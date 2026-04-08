# 04 - Gateway Delivery

## Preconditions

- You already validated the same file with `--dry-run`.
- You have a valid Bearer token.
- You know the gateway base URL.

## Delivery example

```bash
export AUTH_TOKEN="<bearer-token>"

PYTHONPATH=src python3.11 -m adapter_ingestion \
  --manufacturer qvet \
  --input "/path/to/qvet-export.xlsx" \
  --issuer-did "did:web:<example>.globaldatacare.es:employee:<email>:<role>" \
  --audience-did "did:web:<clinic>.globaldatacare.es" \
  --species-catalog-file "./configs/clinic-acme.species.catalog.json" \
  --species-local-map-file "./configs/clinic-acme.species.map.json" \
  --schema-config-file "./configs/clinic-acme.qvet.schema.json" \
  --gateway-base-url "https://gateway.example.com" \
  --resource-route-prefix "/v1" \
  --auth-token "$AUTH_TOKEN" \
  --output-dir ./artifacts/qvet \
  --send
```

## Where `AUTH_TOKEN` comes from

The CLI does not implement interactive login.

Typical options:

1. A token issued by your corporate backend or identity provider.
2. A Google identity token, but only if your gateway is configured to accept it.

Example using Google Cloud CLI:

```bash
gcloud auth login
export AUTH_TOKEN="$(gcloud auth print-identity-token --audiences="<GOOGLE_OAUTH_CLIENT_ID>")"
```

Notes:

- Tokens usually expire in about one hour.
- If the gateway rejects the audience, expect `401` or `403`.

## Route shape

The preferred route format uses `--resource-route-prefix`, for example `/v1`.

Legacy segments such as `--tenant-id`, `--jurisdiction`, and `--sector` are still available for compatibility but are no longer required for the main DIDComm flow.

## What is delivered

The CLI posts the `Composition` batch to `.../Composition/_batch`.

## Expected console output

- One HTTP status per POST request
- `location` when the gateway returns it

## Recommended operating practice

- Start a new clinic with small batches.
- Record the source file, the timestamp, and the associated `summary.json`.
- Preserve generated artifacts on HTTP failure so you can retry without reprocessing the original export.
