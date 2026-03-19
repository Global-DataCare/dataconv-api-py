#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Configuracion rapida para clinica / IT
# Edita estos valores y ejecuta:
#   ./scripts/run-clinic-ingestion.sh dry-run
#   ./scripts/run-clinic-ingestion.sh send
# ============================================================

# --- Runtime ---
PYTHON_BIN="python3"

# --- Datos de carga ---
MANUFACTURER="wakyma"            # qvet | wakyma
INPUT_FILE="/Users/fernando/GITS/gdc-workspace/Informes - Explorador de Visitas (Wakyma).xlsx"
TENANT_ID=""                      # opcional (ruta con segmentos tenant/country/sector)
JURISDICTION=""                   # opcional (ruta con segmentos tenant/country/sector)
SECTOR=""                         # opcional (ruta con segmentos tenant/country/sector)

# --- DIDs ---
ISSUER_DID="did:web:<example>.globaldatacare.es:employee:<email>:<rol>"
AUDIENCE_DID="did:web:<clinica>.globaldatacare.es"

# --- Gateway ---
GATEWAY_BASE_URL="http://localhost:3000"
# Si no usas tenant/jurisdiction/sector, esta es la base de ruta para _batch:
RESOURCE_ROUTE_PREFIX="/v1"
# Token (preferido por entorno): export AUTH_TOKEN="<token>"
AUTH_TOKEN="${AUTH_TOKEN:-}"      # obligatorio si usas modo send

# --- Config de transformacion ---
# Catalogo FHIR estatico (code -> display EN)
SPECIES_CATALOG_FILE="./configs/fhir-target-species.template.editable.json"
SCHEMA_CONFIG_FILE="./configs/wakyma.schema.example.json"

# Lista base recomendada (ES) local text -> FHIR code
SPECIES_LOCAL_MAP_FILE="./configs/clinic-species-map.example.json"

# Opcional: campos mostrados en XHTML. Vacio = todas las columnas
INCLUDE_FIELDS="Tipo,Motivo,Mascota,ID Interno Paciente,Fecha+Hora"

# Identidad sujeto
SUBJECT_DID_PREFIX="did:web:<clinica>.globaldatacare.es"
SUBJECT_KIND="animal"             # animal | species

# Operacion
ALLOW_UNMAPPED_SPECIES="true"     # true para onboarding; false para estricto
EXPORT_SPECIES_TEMPLATE=""        # ejemplo: ./artifacts/species-template.json
OUTPUT_DIR="./artifacts/manual-run"

# ============================================================

MODE="${1:-dry-run}"              # dry-run | send
if [[ "$MODE" != "dry-run" && "$MODE" != "send" ]]; then
  echo "Uso: $0 [dry-run|send]"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_DIR"

if [[ ! -f "$INPUT_FILE" ]]; then
  echo "ERROR: no existe INPUT_FILE: $INPUT_FILE"
  exit 1
fi

if [[ ! -f "$SPECIES_CATALOG_FILE" ]]; then
  echo "ERROR: no existe SPECIES_CATALOG_FILE: $SPECIES_CATALOG_FILE"
  exit 1
fi

if [[ ! -f "$SCHEMA_CONFIG_FILE" ]]; then
  echo "ERROR: no existe SCHEMA_CONFIG_FILE: $SCHEMA_CONFIG_FILE"
  exit 1
fi

if [[ -n "$SPECIES_LOCAL_MAP_FILE" && ! -f "$SPECIES_LOCAL_MAP_FILE" ]]; then
  echo "ERROR: no existe SPECIES_LOCAL_MAP_FILE: $SPECIES_LOCAL_MAP_FILE"
  exit 1
fi

if [[ "$MODE" == "send" && -z "$AUTH_TOKEN" ]]; then
  echo "ERROR: AUTH_TOKEN es obligatorio en modo send"
  exit 1
fi

CMD=(
  "$PYTHON_BIN" -m adapter_ingestion
  --manufacturer "$MANUFACTURER"
  --input "$INPUT_FILE"
  --issuer-did "$ISSUER_DID"
  --audience-did "$AUDIENCE_DID"
  --gateway-base-url "$GATEWAY_BASE_URL"
  --resource-route-prefix "$RESOURCE_ROUTE_PREFIX"
  --species-catalog-file "$SPECIES_CATALOG_FILE"
  --schema-config-file "$SCHEMA_CONFIG_FILE"
  --subject-did-prefix "$SUBJECT_DID_PREFIX"
  --subject-kind "$SUBJECT_KIND"
  --output-dir "$OUTPUT_DIR"
)

if [[ -n "$INCLUDE_FIELDS" ]]; then
  CMD+=(--include-fields "$INCLUDE_FIELDS")
fi

if [[ -n "$SPECIES_LOCAL_MAP_FILE" ]]; then
  CMD+=(--species-local-map-file "$SPECIES_LOCAL_MAP_FILE")
fi

if [[ -n "$TENANT_ID" ]]; then
  CMD+=(--tenant-id "$TENANT_ID")
fi
if [[ -n "$JURISDICTION" ]]; then
  CMD+=(--jurisdiction "$JURISDICTION")
fi
if [[ -n "$SECTOR" ]]; then
  CMD+=(--sector "$SECTOR")
fi

if [[ "$ALLOW_UNMAPPED_SPECIES" == "true" ]]; then
  CMD+=(--allow-unmapped-species)
fi

if [[ -n "$EXPORT_SPECIES_TEMPLATE" ]]; then
  CMD+=(--export-species-template "$EXPORT_SPECIES_TEMPLATE")
fi

if [[ "$MODE" == "send" ]]; then
  CMD+=(--auth-token "$AUTH_TOKEN" --send)
else
  CMD+=(--dry-run)
fi

echo "Ejecutando en modo: $MODE"
echo "Repo: $REPO_DIR"
echo "Fabricante: $MANUFACTURER"
echo "Input: $INPUT_FILE"
echo "Output: $OUTPUT_DIR"
echo

PYTHONPATH=src "${CMD[@]}"

echo
echo "OK. Revisa: $OUTPUT_DIR/summary.json"
