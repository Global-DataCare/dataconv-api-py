#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
ALT="${ALT:-acme}"
JUR="${JUR:-ES}"
SECTOR="${SECTOR:-onehealth-research}"
SOFTWARE_ID="${SOFTWARE_ID:-qvet-v1.0}"
RESOURCE_TYPE="${RESOURCE_TYPE:-Composition}"
ISS="${ISS:-did:web:clinic.example:employee:it:loader}"
DROPBOX_URL="${DROPBOX_URL:-https://www.dropbox.com/scl/fi/gkc57co2y9litpm7t81vt/exampleQvetES.xlsx?rlkey=5cnesxdtop8hfdryhrrlmo89w&st=1rsqrcqp&dl=1}"
OUT_DIR="${OUT_DIR:-artifacts/integrator-smoke}"
POLL_SECONDS="${POLL_SECONDS:-2}"
MAX_POLLS="${MAX_POLLS:-30}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
AUTH_TOKEN="${AUTH_TOKEN:-demo-token}"

RUN_ID="$(date +%Y%m%dT%H%M%S)-$(uuidgen | tr 'A-Z' 'a-z')"
NOW="$(date +%s)"
EXP="$((NOW + 600))"
CFG_THID="cfg-${RUN_ID}"
UP_THID="up-${RUN_ID}"

REQUESTS_DIR="${OUT_DIR}/requests/${RUN_ID}"
RESPONSES_DIR="${OUT_DIR}/responses/${RUN_ID}"
mkdir -p "${REQUESTS_DIR}" "${RESPONSES_DIR}"

AUTH_ARGS=()
if [[ -n "${AUTH_TOKEN}" ]]; then
  AUTH_ARGS=(-H "Authorization: Bearer ${AUTH_TOKEN}")
fi

write_file() {
  local path="$1"
  shift
  cat >"${path}" <<EOF
$*
EOF
}

post_json() {
  local url="$1"
  local payload_file="$2"
  local body_file="$3"
  local headers_file="$4"
  local status_file="$5"

  local http_code
  http_code="$(
    curl -sS \
      "${AUTH_ARGS[@]:+${AUTH_ARGS[@]}}" \
      -H "Content-Type: application/didcomm-plain+json" \
      -X POST "${url}" \
      --data @"${payload_file}" \
      -D "${headers_file}" \
      -o "${body_file}" \
      -w "%{http_code}"
  )"
  printf '%s\n' "${http_code}" >"${status_file}"
}

read_status_field() {
  local json_file="$1"
  "${PYTHON_BIN}" - "${json_file}" <<'PY'
import json
import sys

path = sys.argv[1]
try:
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
except Exception:
    print("")
    raise SystemExit(0)

body = payload.get("body", {}) if isinstance(payload, dict) else {}
issues = body.get("issues", {}) if isinstance(body, dict) else {}
issue_list = issues.get("issue", []) if isinstance(issues, dict) else []
codes = []
for item in issue_list:
    if isinstance(item, dict):
        code = str(item.get("code", "")).strip()
        if code:
            codes.append(code)

data = body.get("data", []) if isinstance(body, dict) else []
has_resource = False
if isinstance(data, list):
    for item in data:
        if isinstance(item, dict) and item.get("resource"):
            has_resource = True
            break

summary = {
    "issueCodes": codes,
    "hasResource": has_resource,
    "total": body.get("total", 0) if isinstance(body, dict) else 0,
}
print(json.dumps(summary, ensure_ascii=True))
PY
}

CONFIG_CREATE_FILE="${REQUESTS_DIR}/01-config-create.didcomm.json"
CONFIG_CREATE_POLL_FILE="${REQUESTS_DIR}/02-config-create-response.didcomm.json"
UPLOAD_LINK_FILE="${REQUESTS_DIR}/03-upload-link.didcomm.json"
UPLOAD_POLL_FILE="${REQUESTS_DIR}/04-upload-response.didcomm.json"
RUN_META_FILE="${REQUESTS_DIR}/00-run-meta.env"

write_file "${RUN_META_FILE}" "BASE_URL=${BASE_URL}
ALT=${ALT}
JUR=${JUR}
SOFTWARE_ID=${SOFTWARE_ID}
SECTOR=${SECTOR}
RESOURCE_TYPE=${RESOURCE_TYPE}
ISS=${ISS}
DROPBOX_URL=${DROPBOX_URL}
RUN_ID=${RUN_ID}
CFG_THID=${CFG_THID}
UP_THID=${UP_THID}
NOW=${NOW}
EXP=${EXP}"

write_file "${CONFIG_CREATE_FILE}" "{
  \"iss\": \"${ISS}\",
  \"thid\": \"${CFG_THID}\",
  \"jti\": \"${CFG_THID}\",
  \"type\": \"https://didcomm.org/plaintext/2.0/message\",
  \"iat\": ${NOW},
  \"exp\": ${EXP},
  \"body\": {
    \"resourceType\": \"Bundle\",
    \"type\": \"batch\",
    \"data\": [
      {
        \"softwareId\": \"${SOFTWARE_ID}\",
        \"config\": {
          \"mappingConfig\": {
            \"headerRowIndex\": 1,
            \"fieldMap\": {
              \"section\": \"SECCION\",
              \"family\": \"FAMILIA\",
              \"subfamily\": \"SUBFAMILIA\",
              \"concept\": \"CONCEPTO\",
              \"subjectId\": \"HISTORIA_ID\",
              \"species\": \"ESPECIE\",
              \"sourceId\": \"IDARTICULO\",
              \"date\": \"FECHA\",
              \"time\": \"HORA\"
            }
          }
        }
      }
    ],
    \"total\": 1
  }
}"

write_file "${CONFIG_CREATE_POLL_FILE}" "{
  \"iss\": \"${ISS}\",
  \"thid\": \"${CFG_THID}\",
  \"type\": \"https://didcomm.org/plaintext/2.0/message\",
  \"iat\": ${NOW},
  \"exp\": ${EXP}
}"

write_file "${UPLOAD_LINK_FILE}" "{
  \"iss\": \"${ISS}\",
  \"thid\": \"${UP_THID}\",
  \"jti\": \"${UP_THID}\",
  \"type\": \"https://didcomm.org/plaintext/2.0/message\",
  \"iat\": ${NOW},
  \"exp\": ${EXP},
  \"sourceFormat\": \"excel\",
  \"body\": {
    \"resourceType\": \"Bundle\",
    \"type\": \"batch\",
    \"data\": [],
    \"total\": 0
  },
  \"attachments\": [
    {
      \"id\": \"source-xlsx\",
      \"media_type\": \"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\",
      \"filename\": \"exampleQvetES.xlsx\",
      \"data\": {
        \"links\": [\"${DROPBOX_URL}\"]
      }
    }
  ]
}"

write_file "${UPLOAD_POLL_FILE}" "{
  \"iss\": \"${ISS}\",
  \"thid\": \"${UP_THID}\",
  \"type\": \"https://didcomm.org/plaintext/2.0/message\",
  \"iat\": ${NOW},
  \"exp\": ${EXP}
}"

post_json \
  "${BASE_URL}/host/cds-${JUR}/v1/${SECTOR}/${ALT}/${SOFTWARE_ID}/config/_create" \
  "${CONFIG_CREATE_FILE}" \
  "${RESPONSES_DIR}/01-config-create.body.txt" \
  "${RESPONSES_DIR}/01-config-create.headers.txt" \
  "${RESPONSES_DIR}/01-config-create.http-status.txt"

post_json \
  "${BASE_URL}/host/cds-${JUR}/v1/${SECTOR}/${ALT}/${SOFTWARE_ID}/config/_create-response?thid=${CFG_THID}" \
  "${CONFIG_CREATE_POLL_FILE}" \
  "${RESPONSES_DIR}/02-config-create-response.json" \
  "${RESPONSES_DIR}/02-config-create-response.headers.txt" \
  "${RESPONSES_DIR}/02-config-create-response.http-status.txt"

post_json \
  "${BASE_URL}/${ALT}/cds-${JUR}/v1/${SECTOR}/digitaltwin/${SOFTWARE_ID}/${RESOURCE_TYPE}/_upload" \
  "${UPLOAD_LINK_FILE}" \
  "${RESPONSES_DIR}/03-upload.body.txt" \
  "${RESPONSES_DIR}/03-upload.headers.txt" \
  "${RESPONSES_DIR}/03-upload.http-status.txt"

final_status=""
final_summary=""
for poll_idx in $(seq 1 "${MAX_POLLS}"); do
  poll_body="${RESPONSES_DIR}/04-upload-response.poll-${poll_idx}.json"
  poll_headers="${RESPONSES_DIR}/04-upload-response.poll-${poll_idx}.headers.txt"
  poll_http="${RESPONSES_DIR}/04-upload-response.poll-${poll_idx}.http-status.txt"

  post_json \
    "${BASE_URL}/${ALT}/cds-${JUR}/v1/${SECTOR}/digitaltwin/${SOFTWARE_ID}/${RESOURCE_TYPE}/_upload-response?thid=${UP_THID}" \
    "${UPLOAD_POLL_FILE}" \
    "${poll_body}" \
    "${poll_headers}" \
    "${poll_http}"

  final_status="$(cat "${poll_http}")"
  final_summary="$(read_status_field "${poll_body}")"
  if [[ "${final_status}" == "200" ]]; then
    cp "${poll_body}" "${RESPONSES_DIR}/04-upload-response.final.json"
    cp "${poll_headers}" "${RESPONSES_DIR}/04-upload-response.final.headers.txt"
    cp "${poll_http}" "${RESPONSES_DIR}/04-upload-response.final.http-status.txt"
    break
  fi

  sleep "${POLL_SECONDS}"
done

printf 'Smoke run saved in %s\n' "${OUT_DIR}"
printf 'Requests: %s\n' "${REQUESTS_DIR}"
printf 'Responses: %s\n' "${RESPONSES_DIR}"
printf 'Final upload HTTP: %s\n' "${final_status:-unknown}"
printf 'Final upload summary: %s\n' "${final_summary:-unknown}"

if [[ "${final_status}" != "200" ]]; then
  printf 'Upload did not reach HTTP 200 within MAX_POLLS=%s\n' "${MAX_POLLS}" >&2
  exit 1
fi
