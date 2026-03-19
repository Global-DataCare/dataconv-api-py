# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any
import json


def load_example_json(relative_path: str) -> dict[str, Any]:
    search_roots = (
        Path(__file__).resolve().parents[3],
        Path.cwd(),
        Path("/app"),
    )
    for root in search_roots:
        try:
            candidate = root / relative_path
            if not candidate.is_file():
                continue
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return {}
