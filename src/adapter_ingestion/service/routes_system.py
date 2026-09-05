# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
from __future__ import annotations

import json
from pathlib import Path

from gdc_data_utils import ChargeItemClaim, DiagnosticReportClaim, InvoiceClaim

from .api_support import HTMLResponse, build_api_docs_html
from ..base_config_contract import BASE_CONFIG_FIELDS, BaseConfigFieldKind


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
            DiagnosticReportClaim.CODE_TEXT: "Nombre o diagnóstico local sin código terminológico",
        }
        pending_fields = {
            name: entry.note
            for name, entry in BASE_CONFIG_FIELDS.items()
            if entry.kind is BaseConfigFieldKind.PENDING
        }
        field_aliases = {
            name: entry.canonical_claim
            for name, entry in BASE_CONFIG_FIELDS.items()
            if entry.kind is BaseConfigFieldKind.CANONICAL_CLAIM
        }
        for pending_name in pending_fields:
            supported_fields.pop(pending_name, None)
        for alias_name, claim_name in field_aliases.items():
            description = supported_fields.pop(alias_name, "Canonical flat FHIR-like claim")
            supported_fields.setdefault(claim_name, description)
        supported_fields.update({
            InvoiceClaim.IDENTIFIER: "Stable business invoice identifier",
            InvoiceClaim.DATE: "Invoice issue date/time",
            ChargeItemClaim.IDENTIFIER: "Stable invoice-line identifier",
            ChargeItemClaim.CODE: "Public product or service code",
            ChargeItemClaim.CODE_TEXT: "Local-language product or service text",
            ChargeItemClaim.QUANTITY_NUMBER: "Numeric charged quantity",
            ChargeItemClaim.QUANTITY_UNIT: "UCUM-like charged quantity unit",
            ChargeItemClaim.SUPPORTING_INFORMATION: (
                "Supporting Invoice reference; never encoded as ChargeItem.part-of"
            ),
        })
        payload = {
            "language": settings.iclaims_locale,
            "supportedFields": supported_fields,
            "fieldAliases": field_aliases,
            "pendingFields": pending_fields,
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
