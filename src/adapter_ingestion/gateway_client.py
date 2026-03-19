# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import json


@dataclass(frozen=True)
class GatewayResponse:
    status: int
    body: str
    location: str | None


def post_didcomm_plaintext(
    base_url: str,
    route_path: str,
    bearer_token: str,
    payload: dict[str, Any],
    timeout_seconds: int = 30,
) -> GatewayResponse:
    if not bearer_token:
        raise ValueError("Bearer token is required when send mode is enabled.")

    target_url = urljoin(base_url.rstrip("/") + "/", route_path.lstrip("/"))
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        target_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/didcomm-plain+json",
            "Authorization": f"Bearer {bearer_token}",
        },
    )

    with urlopen(request, timeout=timeout_seconds) as response:
        response_body = response.read().decode("utf-8", errors="replace")
        return GatewayResponse(
            status=response.status,
            body=response_body,
            location=response.headers.get("Location"),
        )
