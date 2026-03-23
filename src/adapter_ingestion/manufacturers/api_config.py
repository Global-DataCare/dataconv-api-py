# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from .qvet import QvetAdapter


class ApiConfigAdapter(QvetAdapter):
    name = "api-config"
    source_namespace = "api-config"
