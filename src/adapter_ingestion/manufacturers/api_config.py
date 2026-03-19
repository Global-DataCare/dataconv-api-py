# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from .tabular_xlsx import TabularXlsxAdapter


class ApiConfigAdapter(TabularXlsxAdapter):
    name = "api-config"
    source_namespace = "api-config"
