# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import json
import logging
import os


LOGGER_NAME = "preconversion.events"


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def configure_logging() -> None:
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(level=logging.INFO, format="%(message)s")


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool, dict, list)):
            normalized[key] = value
        else:
            normalized[key] = str(value)
    return normalized


def log_event(event: str, **fields: Any) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    payload: dict[str, Any] = {
        "ts": _now_iso_utc(),
        "event": str(event or "").strip() or "unknown",
        "service": os.getenv("ICLAIMS_APP_ID", "preconversion-api"),
    }
    payload.update(_normalize_payload(fields))
    logger.info(json.dumps(payload, ensure_ascii=True, sort_keys=True))

