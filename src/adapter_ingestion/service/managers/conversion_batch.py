# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from .conversion_promotion import promote_resources
from .dependencies import ApiManagerDependencies


class ConversionBatchManager:
    def __init__(self, deps: ApiManagerDependencies) -> None:
        self._deps = deps

    def handle(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        software_id: str,
        resource_type: str,
        response: Any,
        request: Any,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        return promote_resources(
            deps=self._deps,
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
            sector=sector,
            resource_type=resource_type,
            request=request,
            body=body,
            source="batch-endpoint",
        )
