# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
from __future__ import annotations

import json
from pathlib import Path

from .api_support import HTMLResponse, build_api_docs_html


def register_system_routes(app, settings) -> None:  # type: ignore[no-untyped-def]
    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {
            "status": "ok",
            "appId": settings.iclaims_app_id,
            "vertical": settings.iclaims_vertical,
            "locale": settings.iclaims_locale,
            "codeDomain": settings.iclaims_code_domain,
            "inferenceDomain": settings.iclaims_inference_domain,
        }

    @app.get("/.well-known/api-config.json", include_in_schema=False)
    def api_config_well_known() -> dict[str, object]:
        supported_fields = {
            "section": "Departamento o sección: tienda, clínica, farmacia, etc. (service-reference)",
            "family": "Categoría de este registro de datos: consulta, revisión, cirugía...",
            "subfamily": "Sub-categoría de este registro de datos: tipo de test, tipo de procedimiento...",
            "concept": "Descripción de este registro de datos (producto o servicio usado/realizado)",
            "date": "Fecha (puede incluir hora)",
            "time": "Hora",
            "origin": "Origen del dato o del sujeto (criador, refugio, etc.)",
            "personal_id": "Evitar si hay ID interno: API siempre lo convierte a un identificador aleatorio",
            "subject_id": "ID interno del sujeto/cliente (no ID público)",
            "subject_address-country": "País del sujeto",
            "subject_address-postalcode": "Código postal del cliente: Solo animales",
            "subject_animal-species": "Especie: Solo animales",
            "subject_animal-breeds": "Raza: Solo animales",
            "subject_birthyear": "Se eliminarán el mes y el día",
            "subject_birthsex": "Sexo biológico al nacer",
            "subject_animal-genderstatus": "Solo animales: se convierte a \"neutered\" o \"intact\"",
            "subject_gender": "Género",
            "appointment_lastoccurrencedate": "Fecha de la visita anterior",
            "encounter_participant-type-display": "Categoría profesional del empleado que atendió al cliente",
            "encounter_service-type-display": "Tipo de servicio prestado",
            "chargeitem_identifier": "Código (comercial) del producto o servicio usado/realizado",
            "coverage_insurer": "Identificador o nombre de la aseguradora",
            "coverage_status": "Estado del seguro de salud (solo animales)",
            "coverage_period-start": "Fecha de inicio de la cobertura (solo animales)",
            "coverage_period-end": "Fecha de finalzación de la cobertura (solo animales)",
            "location_address-postalcode": "Generador del dato: código postal",
            "location_address-city": "Generador del dato: municipio",
            "location_address-district": "Generador del dato: provincia",
            "location_address-state": "Generador del dato: CC.AA.",
            "observation_weight": "Peso (o rango estimado)",
            "procedure_code-display": "Código de procedimiento realizado",
            "procedure_followup-date": "Fecha recomendada para el siguiente tratamiento",
            "procedure_subpotent-date": "Fecha en la que expira el efecto del tratamiento",
            "procedure_target-display": "Problemas que cubre este tratamiento",
        }
        payload = {
            "language": settings.iclaims_locale,
            "supportedFields": supported_fields,
            "allowedJurisdictions": list(getattr(settings, "supported_jurisdictions", ("*",))),
            "allowedSectors": list(getattr(settings, "supported_sectors", ("*",))),
            "auth": {
                "exchangeEndpoint": "/exchange",
                "oauthTokenEndpoint": "/oauth/token",
                "subjectTokenType": "urn:ietf:params:oauth:token-type:id_token",
                "clientAssertionType": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                "apiKeySupported": bool(getattr(settings, "exchange_allow_api_key", False)),
            },
            "endpoints": {
                "create": "/host/cds-{jurisdiction}/v1/{sector}/{tenant_id}/{software_id}/config/_create",
                "createResponse": "/host/cds-{jurisdiction}/v1/{sector}/{tenant_id}/{software_id}/config/_create-response",
                "upload": "/host/cds-{jurisdiction}/v1/{sector}/{tenant_id}/{software_id}/config/_upload",
                "uploadResponse": "/host/cds-{jurisdiction}/v1/{sector}/{tenant_id}/{software_id}/config/_upload-response",
            },
        }
        try:
            artifact_dir = Path("artifacts/.well-known")
            artifact_dir.mkdir(parents=True, exist_ok=True)
            with open(artifact_dir / "api-config.json", "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return payload

    @app.get("/.wellknown/api-docs", include_in_schema=False)
    def api_docs_wellknown_alias() -> dict[str, object]:
        return api_config_well_known()

    @app.get("/api-docs", include_in_schema=False, response_class=HTMLResponse)
    def api_docs() -> str:
        return build_api_docs_html(openapi_url="/openapi.json")
