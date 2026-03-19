# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

from ..models import AdapterContext, CanonicalRecord


class ManufacturerAdapter:
    name: str

    def read_records(self, input_path: Path, context: AdapterContext) -> list[CanonicalRecord]:
        raise NotImplementedError

    def get_last_report(self) -> dict:
        return {}
