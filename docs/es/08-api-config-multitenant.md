# 08 - Configuración Multi-tenant para API (reutilización)

Objetivo: que el adaptador actual se reutilice desde una API, manteniendo configuración por clínica (tenant) con contrato DIDComm/FAPI claro para integradores.

Este documento asume una API de iClaims por vertical/idioma (por ejemplo `vet-claims-api`).

## 1) Contrato de configuración por tenant

Usar un documento de configuración único por `(tenantDid, softwareId)`, donde:
- `softwareId` es el nombre público recomendado (ej. `qvet-v1.0`).
- Internamente se separa en `manufacturer=qvet` + `manufacturerVersion=v1.0`.

Ejemplo de payload:

- `configs/tenant-adapter-config.api.example.json`

Campos clave:

- `config.mappingConfig`: columnas, filtros, `loincBySectionFamily`.
- `config.mappingConfig.excludedSectionFamilies`: deny-list opcional por `section:family` para excluir datos del procesamiento (ej. `clinica:vacunas`).
- `config.speciesFhir`: catálogo FHIR species estático (`code -> display EN`). Opcional; normalmente **no hace falta enviarlo**.
- `config.speciesLocalToFhirCode`: texto local -> código FHIR (común por clínica, no anidado).
- `config.runtimeDefaults`: opciones por defecto para ejecución.

Definición técnica de `mappingConfig`:

- Contrato OpenAPI (Swagger): `SchemaConfig` en `src/adapter_ingestion/service/openapi_contract.py`.
- Normalización XLSX/CSV: `src/adapter_ingestion/manufacturers/tabular_xlsx.py`.
- Aplicación en pipeline (claims): `src/adapter_ingestion/pipeline.py`.

Claves activas de `mappingConfig` (actual):

- `headerRowIndex`
- `fieldMap`
- `fieldDefaults`
- `speciesContains`
- `allowedSections`
- `excludedSections`
- `excludedSectionFamilies`
- `ownerPublicRules`
- `loincBySectionFamily`
- `encounterClassBySectionFamily`
- `encounterServiceTypeBySectionFamily`

Notas:

- `patientRules` era legado/no-op y ya no forma parte del contrato recomendado.
- Si envías claves extra no soportadas, hoy se almacenan pero el runtime las ignora.

Desglose práctico de cada entry en `data[]`:

- `softwareId` (obligatorio, recomendado): token del software + versión, por ejemplo `qvet-v1.0`.
- `config` (recomendado): objeto de configuración del adaptador.
- `config.mappingConfig` (recomendado): mapeo de columnas/filtros del exportador.
  - `headerRowIndex` dentro de `mappingConfig` indica la fila de cabecera real del Excel (empieza en 1).
  - Ejemplo: si fila 1 es título y la cabecera está en fila 2, usar `headerRowIndex=2`.
- `config.mappingConfig.excludedSectionFamilies` (opcional recomendado): exclusiones por categoría. Si una fila coincide, no se procesa ni se devuelve en `body.data[]`.
- `config.speciesLocalToFhirCode` (recomendado): traducción de textos locales (`Perro`, `CANINA`, etc.) a código FHIR.
- `config.runtimeDefaults` (opcional): defaults de ejecución (`language`, `dataUse`, etc.).
- `config.speciesFhir` (opcional avanzado): solo enviar si quieres sobrescribir el catálogo base del servidor.
  - Si no se envía, la API usa el catálogo por defecto (`PRECONV_DEFAULT_SPECIES_FHIR_FILE`).

Nota sobre `sourceId`:
- Es opcional.
- Si no se define en `fieldMap`, el adaptador genera un id estable por fila (hash de contenido relevante).

## 2) Reglas de versionado recomendadas

- Clave funcional pública: `(tenantDid, softwareId)`.
- La API debe guardar también `updatedAt`, `revision` y actor en `audit.updatedBy`.
- No sobrescribir en caliente sin control de revisión (optimistic lock por `revision`).

## 3) Endpoints implementados (patrón gateway, POST-only, request/response)

1. `POST /host/cds-{jurisdiction}/v1/animal-care/{alternate-name}/config/didcomm/_create`
Request de alta/actualización de configuración por organización (acepta una o varias entries en `body.data[]`).
Cada item de `data[]` es un objeto de configuración directo (sin wrapper `payload`), usando `config` como wrapper interno.

2. `POST /host/cds-{jurisdiction}/v1/animal-care/{alternate-name}/config/didcomm/_create-response`
Retrieve de respuesta de `_create` por `thid` (patrón `action` -> `action-response`).

3. `POST /{alternate-name}/cds-{jurisdiction}/v1/animal-care/conversion/{software-id}/{csv|excel}/_upload`
Request de subida y encolado asíncrono de conversión.

4. `POST /{alternate-name}/cds-{jurisdiction}/v1/animal-care/conversion/{software-id}/{csv|excel}/_upload-response`
Retrieve de estado/resultado asíncrono por `thid` (patrón `action` -> `action-response`).

Respuesta:
- `_create` devuelve `202` solo con cabeceras `Location` (`.../_create-response`) + `Retry-After` (sin body).
- `_create-response` devuelve `200` con un mensaje DIDComm-like cuyo `body.resourceType="Bundle"` y `body.type="batch-response"`.
- El `Bundle` de `_create-response` incluye `body.issues` (OperationOutcome global, estilo R5) además de las entradas por item.
- En `_create-response`, cada `body.data[]` entry incluye `response.status` y `response.outcome` (`OperationOutcome`).
- En `_create-response`, `body.data[].resource` devuelve el objeto de configuración persistido (`id`, `type`, `content`, `revision`, `createdAt`, `updatedAt`, `audit`), más metadatos (`alternateName`, `softwareId`, etc.).
- Si una entrada de configuración falla, también se devuelve su `body.data[].resource` (preview de esa configuración) junto con `response.status` y `response.outcome`.
- Si hay error de validación/auth en `_create` (con `thid`), el resultado aparece en `_create-response` como entry con `response.status` `4xx/5xx` y `response.outcome`.
- `_create-response` es de consumo único (semántica POP): al leerlo una vez, deja de estar disponible.
- `_upload` devuelve `202` sin body funcional; la app cliente usa headers HTTP:
- `Location`: endpoint `.../_upload-response` para polling.
- `Retry-After`: espera recomendada antes del siguiente poll.
- `_upload-response` devuelve `202` mientras el job está en `queued/running` y `200` al finalizar (`succeeded/failed`).
- Si `_upload-response` está en `queued`, devuelve un `Bundle` `batch-response` con `body.data[0].response.queuePosition` (estimación de posición en cola).
- Cuando `_upload-response` devuelve `200`, `body.data[0]` representa el input procesado y `body.data[0].resource` contiene el `Bundle` convertido.
- En la respuesta inicial `202` de `_create` (la que devuelve `Location`) no se devuelve `thid`.
- En polling (`_create-response` / `_upload-response`) sí puede devolverse `thid`.
- Si faltan mapeos `section:family -> LOINC`, esas filas se omiten.
- Por cada fila omitida se añade un recurso `OperationOutcome` dentro del `Bundle` convertido (`body.data[0].resource.data[]`).
- El diagnóstico agregado también se expone en `body.issues.issue[].diagnostics` y en `body.data[0].response.outcome.issue[].diagnostics`.
- Las respuestas terminales de `_upload-response` expiran según `PRECONV_JOB_RESULT_TTL_SECONDS` (por defecto 3600s).
- La limpieza global (todos los tenants) se ejecuta con `preconversion-cleanup` y se recomienda programarla con cron/CronJob.
- Errores del contrato público se devuelven como `OperationOutcome` (`400/401/403/404/500`); no se documenta `422`.
- El lifecycle deja trazas JSON estructuradas en logs (`job_created`, `job_response_delivered`, `job_expired_deleted`, `job_cleanup_*`) con `tenantId`, `softwareId`, `thid`, `jobId`, etc.

Bootstrap automático:
- En `POST .../_upload`, si no existe config para el selector, la API crea una config base automáticamente con:
- `fieldMap` estándar: `SECTION/FAMILY/SUBFAMILY/CONCEPT/SUBJECT_ID/SPECIES/DATE/TIME`.
- `speciesFhir` cargado desde `PRECONV_DEFAULT_SPECIES_FHIR_FILE`.
- `speciesLocalToFhirCode` vacío (solo debes rellenar textos locales de especie).
- `runtimeDefaults.language` opcional: si no se define, se deriva de `country/jurisdiction` (ej. `es` -> `es-ES`).
- `runtimeDefaults.dataUse` opcional: `secondary` (default API) u `individual`.

Entrada de `_upload`:
- Recomendado: `multipart/form-data` con `file`.
- Alternativa pública equivalente: `application/didcomm-plain+json` con `attachments[]`.
- `iss` es obligatorio y debe ser `did:web` de empleado o sistema.
- `type` es obligatorio en el envelope DIDComm/FAPI.
- `thid` obligatorio para correlación asíncrona.
- `jti` es opcional (anti-replay/id de mensaje). `iat` y `exp` son obligatorios (`exp >= iat`).
- `requestedBy` no forma parte del contrato público; la API lo deriva de `iss`.
- `facilityId` está reservado para futuro y hoy se ignora en el contrato público.
- En `attachments[].data` se admite:
- `base64` para enviar el Excel inline.
- `links[]` para que la API descargue el Excel desde una URL HTTP(S).
- Para Dropbox compartido, usar `dl=1`; si llega `dl=0`, la API intenta normalizarlo antes de descargar.
- `gzip` soportado únicamente por header HTTP `Content-Encoding: gzip`.
- No usar `PUT/GET` en el flujo de negocio; el contrato público es `POST` únicamente.

Nota de operación:
- El contrato público para clientes es el bloque de endpoints DIDComm anterior (`_create`, `_create-response`, `_upload`, `_upload-response`).

## 4) Ejemplo mínimo de `_upload` y `_upload-response`

Subida de Excel con `multipart/form-data`:

```bash
curl -X POST "https://<host>/<alternate-name>/cds-ES/v1/animal-care/conversion/qvet-v1.0/excel/_upload" \
  -F "file=@/ruta/export.xlsx" \
  -F "iss=did:web:clinic.example:employee:it:loader" \
  -F "type=https://didcomm.org/plaintext/2.0/message" \
  -F "thid=<uuid>" \
  -F "jti=<uuid>" \
  -F "iat=1760000000" \
  -F "exp=1760003600"
```

Subida DIDComm con `attachments[]` y URL externa:

```bash
curl -X POST "https://<host>/<alternate-name>/cds-ES/v1/animal-care/conversion/qvet-v1.0/excel/_upload" \
  -H "Content-Type: application/didcomm-plain+json" \
  -d '{\
    "iss":"did:web:clinic.example:employee:it:loader",\
    "type":"https://didcomm.org/plaintext/2.0/message",\
    "thid":"<uuid>",\
    "jti":"<uuid>",\
    "iat":1760000000,\
    "exp":1760003600,\
    "body":{"resourceType":"Bundle","type":"batch","data":[],"total":0},\
    "attachments":[{\
      "id":"source-xlsx",\
      "media_type":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",\
      "filename":"export.xlsx",\
      "data":{"links":["https://www.dropbox.com/s/example123/export.xlsx?dl=1"]}\
    }]\
  }'
```

Polling asíncrono:

```bash
curl -X POST "https://<host>/<alternate-name>/cds-ES/v1/animal-care/conversion/qvet-v1.0/excel/_upload-response" \
  -H "Content-Type: application/didcomm-plain+json" \
  -d '{"iss":"did:web:clinic.example:employee:it:loader","type":"https://didcomm.org/plaintext/2.0/message","iat":1760000000,"exp":1760003600,"thid":"<thid-enviado-en-upload>"}'
```

Respuesta final típica (`200`):

```json
{
  "jti": "ec7a9c5e-8fb2-4bd0-8fda-1ec89e110233",
  "thid": "up-1fd4a2d9",
  "iss": "did:web:globaldatacare.es:employee:preconversion",
  "aud": "did:web:clinic.example:employee:it:loader",
  "type": "https://didcomm.org/plaintext/2.0/message",
  "iat": 1760000000,
  "exp": 1760000300,
  "body": {
    "resourceType": "Bundle",
    "type": "batch-response",
    "issues": {
      "resourceType": "OperationOutcome",
      "issue": [
        {
          "severity": "information",
          "code": "informational",
          "diagnostics": "Job status: succeeded"
        }
      ]
    },
    "data": [
      {
        "type": "ConversionResult",
        "resource": {
          "resourceType": "Bundle",
          "type": "batch",
          "data": [
            { "resource": { "resourceType": "Composition" } },
            {
              "resource": { "resourceType": "OperationOutcome" }
            }
          ],
          "total": 2
        },
        "response": {
          "status": "200",
          "outcome": { "resourceType": "OperationOutcome" }
        }
      }
    ],
    "total": 1
  }
}
```

Restricción actual del transporte DIDComm en `_upload`:

- un request procesa un único input
- por tanto se acepta un solo `attachment`
- y cada `attachment.data.links` debe contener una sola URL
- si en el futuro se soporta batch real, entonces sí tendrá sentido mapear `1 attachment -> 1 item de body.data[]`

## 5) Ejemplo Windows (PowerShell)

```powershell
$Base = "https://preconversion.example.globaldatacare.es"
$Alt = "franquicia-x"
$Jur = "ES"
$Man = "qvet-v1.0"
$Iss = "did:web:franquicia-x.globaldatacare.es:employee:it:loader"
$Thid = [guid]::NewGuid().ToString()
$Now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$Exp = $Now + 3600

# 1) crear configuracion
$CreateBody = @"
{
  "iss": "$Iss",
  "thid": "cfg-$Thid",
  "jti": "cfg-$Thid",
  "type": "https://didcomm.org/plaintext/2.0/message",
  "iat": $Now,
  "exp": $Exp,
  "vp_token": "<signed-vp-jwt-with-employee-vc>",
  "data": [
    {
      "softwareId": "$Man",
      "config": {
        "mappingConfig": {
          "headerRowIndex": 2,
          "excludedSectionFamilies": ["clinica:vacunas"],
          "loincBySectionFamily": {
            "clinica:laboratorio": "30954-2",
            "clinica:consultas": "34109-9",
            "clinica:cirugia": "11504-8",
            "clinica:medicamentos": "10160-0",
            "clinica:varios": "11503-0"
          }
        }
      }
    }
  ]
}
"@
curl.exe -sS -X POST "$Base/host/cds-$Jur/v1/animal-care/$Alt/config/didcomm/_create" `
  -H "Content-Type: application/didcomm-plain+json" `
  --data-raw $CreateBody

# 1b) recuperar respuesta de configuracion
$CreatePollBody = "{""iss"":""$Iss"",""type"":""https://didcomm.org/plaintext/2.0/message"",""iat"":$Now,""exp"":$Exp,""thid"":""cfg-$Thid""}"
curl.exe -sS -X POST "$Base/host/cds-$Jur/v1/animal-care/$Alt/config/didcomm/_create-response" `
  -H "Content-Type: application/didcomm-plain+json" `
  --data-raw $CreatePollBody

# 2) subir fichero y encolar
curl.exe -sS -X POST "$Base/$Alt/cds-$Jur/v1/animal-care/conversion/$Man/excel/_upload" `
  -F "file=@C:\ruta\export.xlsx" `
  -F "iss=$Iss" `
  -F "type=https://didcomm.org/plaintext/2.0/message" `
  -F "thid=$Thid" `
  -F "jti=$Thid" `
  -F "iat=$Now" `
  -F "exp=$Exp"

# 3) consultar estado
$PollBody = "{""iss"":""$Iss"",""type"":""https://didcomm.org/plaintext/2.0/message"",""iat"":$Now,""exp"":$Exp,""thid"":""$Thid""}"
curl.exe -sS -X POST "$Base/$Alt/cds-$Jur/v1/animal-care/conversion/$Man/excel/_upload-response" `
  -H "Content-Type: application/didcomm-plain+json" `
  --data-raw $PollBody
```

## 6) Envelope DIDComm/FAPI y compatibilidad

Ejemplo de envío de configuración en `_create` (una entry):

```json
{
  "iss": "did:web:clinic.example:employee:it:admin",
  "type": "https://didcomm.org/plaintext/2.0/message",
  "iat": 1760000000,
  "exp": 1760003600,
  "vp_token": "<signed-vp-jwt-with-employee-vc>",
  "data": [
    {
      "softwareId": "qvet-v1.0",
      "config": {
        "mappingConfig": {
          "headerRowIndex": 2,
          "excludedSectionFamilies": ["clinica:vacunas"],
          "loincBySectionFamily": {
            "clinica:laboratorio": "30954-2",
            "clinica:consultas": "34109-9",
            "clinica:cirugia": "11504-8",
            "clinica:medicamentos": "10160-0",
            "clinica:varios": "11503-0"
          }
        },
        "runtimeDefaults": {
          "language": "es-ES",
          "dataUse": "secondary"
        }
      }
    }
  ]
}
```

Ejemplo con varias configuraciones en `data[]`:

```json
{
  "iss": "did:web:clinic.example:employee:it:admin",
  "type": "https://didcomm.org/plaintext/2.0/message",
  "iat": 1760000000,
  "exp": 1760003600,
  "vp_token": "<signed-vp-jwt-with-employee-vc>",
  "data": [
    {
      "softwareId": "qvet-v1.0",
      "config": {
        "mappingConfig": {
          "headerRowIndex": 2,
          "excludedSectionFamilies": ["clinica:vacunas"],
          "loincBySectionFamily": { "clinica:consultas": "34109-9" }
        }
      }
    },
    {
      "softwareId": "wakyma-v2.4",
      "config": {
        "mappingConfig": {
          "headerRowIndex": 3,
          "excludedSectionFamilies": ["clinica:vacunacion"],
          "loincBySectionFamily": { "clinica:laboratorio": "30954-2" }
        }
      }
    }
  ]
}
```

Notas:
- El cliente debe enviar `iss` en `_create`, `_create-response`, `_upload` y `_upload-response`.
- `iss` debe ser `did:web` de actor `employee` o `system` en el perfil público actual.
- `type` es obligatorio en todos los mensajes DIDComm/FAPI del contrato público.
- Para correlación asíncrona, enviar `thid` y repetirlo en los requests de `_create-response` y `_upload-response`.
- Los campos `iat` y `exp` son obligatorios en el envelope DIDComm/FAPI y se documentan en Swagger.
- Si la solicitud de configuración ya fue aceptada, `_create-response` devuelve `200`.
- Si el job sigue en curso, `_upload-response` devuelve `202` con `Retry-After`.

## 7) Modo de autenticación del envelope (runtime)

Variables de entorno:
- `PRECONV_AUTH_MODE=parse-only|verify-id-token|verify-vp-token|verify-both`
- `PRECONV_AUTH_DISABLED_SUBJECTS` (lista CSV de sujetos desactivados/revocados)
- `PRECONV_AUTH_DISABLED_DEVICES` (lista CSV de dispositivos desactivados/revocados)
- `PRECONV_JOB_RESULT_TTL_SECONDS` (retención de respuesta terminal para `_upload-response`; `-1` desactiva expiración)
- `PRECONV_CLEANUP_SCHEDULE` (solo despliegue K8s; frecuencia del CronJob de limpieza global)

Comportamiento:
- `parse-only` (solo para pruebas internas/demostraciones): no valida firma criptográfica de tokens; extrae claims si hay `id_token`/`vp_token`.
- `verify-id-token`: exige `id_token` en cada request DIDComm pública.
- `verify-vp-token`: exige `vp_token` en cada request DIDComm pública.
- `verify-both`: exige ambos y comprueba coherencia de sujeto entre ambos.

Recomendación de operación:
- En entornos reales, no usar `parse-only`.
- Usar al menos `verify-id-token` (o `verify-vp-token` / `verify-both` según el perfil de confianza requerido).

Bearer en Swagger (Authorize):
- La API acepta `Authorization: Bearer <token>` como fallback de `id_token`.
- El token puede venir de cualquier proveedor de identidad soportado por tu despliegue
  (Google, Microsoft Entra ID, eIDAS u otro equivalente), siempre con la `audience` esperada.
- Ejemplo demo (`PRECONV_AUTH_MODE=parse-only`): `Bearer demo-token`.
- Ejemplo producción (`verify-*`): `Bearer <JWT id_token>`.
- En Swagger -> `Authorize` -> pegar `Bearer <token>`.

Notas operativas:
- En esta fase, `verify-*` valida presencia/formato JWT + coherencia básica; la verificación criptográfica completa se deja para la siguiente iteración.
- Si un sujeto/dispositivo aparece en listas de desactivación/revocación, la API devuelve `403`.

## 8) Qué se reutiliza del repo actual

- Normalización tabular XLSX (`manufacturers/*`, `xlsx_common.py`).
- Pipeline de claims (`pipeline.py`).
- Serialización DIDComm plaintext (`models.py`).
- Tipos y claves de claims FHIR (`fhir_claims.py`).

Contrato de salida actual:

- `body.data[]` contiene objetos con `resource=Patient` (principal por sujeto).
- `resource.meta.claims` guarda claims interoperables de `Patient`.
- `resource.contained[]` incluye `Composition`, `DocumentReference` y `Encounter` del mismo sujeto.
- `resource.contained[].meta.claims` guarda claims interoperables por recurso.

La API solo orquesta:

- identidad/autorización,
- lectura/escritura de configuración por tenant,
- almacenamiento de artefactos,
- ejecución de jobs.

## 9) Arquitectura (pre-conversión + conector)

Separación de responsabilidades:

1. API de pre-conversión (utilizando adaptadores)
- Gestiona configuración por tenant/fabricante/versión.
- Ejecuta transformaciones y genera artefactos normalizados.
- Publica resultados para consumo posterior.

2. API/conector del espacio de datos
- Expone dominios `animal-research` y `animal-care`.
- Consume los resultados preconvertidos.
- Aplica políticas del conector y envío a los endpoints del espacio de datos.
