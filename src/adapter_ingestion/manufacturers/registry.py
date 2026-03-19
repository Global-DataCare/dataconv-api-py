# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from .api_config import ApiConfigAdapter
from .base import ManufacturerAdapter
from .qvet import QvetAdapter
from .wakyma import WakymaAdapter

_ADAPTERS: dict[str, ManufacturerAdapter] = {
    "api-config": ApiConfigAdapter(),
    "qvet": QvetAdapter(),
    "wakyma": WakymaAdapter(),
}


def get_adapter(name: str) -> ManufacturerAdapter:
    key = (name or "").strip().lower()
    if key not in _ADAPTERS:
        supported = ", ".join(sorted(_ADAPTERS.keys()))
        raise ValueError(f"Unknown manufacturer adapter '{name}'. Supported: {supported}")
    return _ADAPTERS[key]


def list_adapters() -> list[str]:
    return sorted(_ADAPTERS.keys())
