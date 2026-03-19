# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from .observability import configure_logging
from .settings import load_settings


def main() -> int:
    configure_logging()
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise RuntimeError(
            "Missing uvicorn dependency. Install with: pip install 'adapter-ingestion-py[api]'"
        ) from exc

    settings = load_settings()
    uvicorn.run(
        "adapter_ingestion.service.api:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
