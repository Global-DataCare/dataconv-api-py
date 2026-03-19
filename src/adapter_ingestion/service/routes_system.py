# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

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

    @app.get("/api-docs", include_in_schema=False, response_class=HTMLResponse)
    def api_docs() -> str:
        return build_api_docs_html(openapi_url="/openapi.json")
