# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Callable, Protocol
from urllib import error, request
import json

from ...runtime import ConfigKey, PreconversionControlPlane
from ..auth_exchange import validate_id_token


class OrganizationProofVerifierClient(Protocol):
    def verify(self, **request_payload: str) -> dict[str, Any]: ...


class ConnectIcaOrganizationProofVerifierClient:
    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: int = 15) -> None:
        self._base_url = str(base_url or "").strip().rstrip("/")
        self._api_key = str(api_key or "").strip()
        self._timeout_seconds = max(1, int(timeout_seconds))
        if not self._base_url or not self._api_key:
            raise ValueError("PRECONV_ICA_BASE_URL and PRECONV_ICA_API_KEY are required")

    def verify(self, **request_payload: str) -> dict[str, Any]:
        jurisdiction = request_payload["jurisdiction"]
        sector = request_payload["sector"]
        network_kind = request_payload["network_kind"]
        url = (
            f"{self._base_url}/internal/ica/cds-{jurisdiction}/v1/{sector}/{network_kind}"
            "/organization/credentials/_verify"
        )
        encoded = json.dumps(
            {
                "tenantId": request_payload["tenant_id"],
                "audience": request_payload["audience"],
                "vpToken": request_payload["vp_token"],
            },
            separators=(",", ":"),
        ).encode("utf-8")
        outgoing = request.Request(
            url,
            data=encoded,
            method="POST",
            headers={
                "authorization": f"Bearer {self._api_key}",
                "content-type": "application/json",
            },
        )
        try:
            with request.urlopen(outgoing, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"Connect ICA rejected organization proof: {detail}") from exc
        except (error.URLError, TimeoutError) as exc:
            raise ValueError(f"Connect ICA organization proof verification unavailable: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("active") is not True:
            raise ValueError("Connect ICA did not confirm active organization credentials")
        return payload


class OrganizationTenantActivationManager:
    def __init__(
        self,
        *,
        settings: Any,
        control_plane: PreconversionControlPlane,
        verifier: OrganizationProofVerifierClient,
        identity_validator: Callable[[str], Any] | None = None,
    ) -> None:
        self._settings = settings
        self._control_plane = control_plane
        self._verifier = verifier
        self._identity_validator = identity_validator or (lambda token: validate_id_token(token, settings))

    def activate(
        self,
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
        id_token: str,
        vp_token: str,
    ) -> dict[str, Any]:
        normalized_tenant = str(tenant_id or "").strip()
        normalized_jurisdiction = str(jurisdiction or "").strip().upper()
        normalized_sector = str(sector or "").strip().lower()
        if not normalized_tenant or not normalized_jurisdiction or not normalized_sector:
            raise ValueError("tenant_id, jurisdiction and sector are required")
        if not str(id_token or "").strip() or not str(vp_token or "").strip():
            raise ValueError("id_token and vp_token are required")
        identity = self._identity_validator(id_token)
        audience = str(getattr(self._settings, "default_audience_did", "") or "").strip()
        network_kind = str(getattr(self._settings, "network_mode", "test") or "test").strip().lower()
        verification = self._verifier.verify(
            tenant_id=normalized_tenant,
            jurisdiction=normalized_jurisdiction,
            sector=normalized_sector,
            network_kind=network_kind,
            audience=audience,
            vp_token=vp_token,
        )
        content = {
            "active": True,
            "networkKind": network_kind,
            "jurisdiction": normalized_jurisdiction,
            "sector": normalized_sector,
            "controller": str(verification.get("controller") or "").strip(),
            "credentialIds": list(verification.get("credentialIds") or []),
            "credentialLedgerChecked": bool(verification.get("ledgerChecked")),
            "activatedBy": str(getattr(identity, "subject", "") or "").strip(),
        }
        stored = self._control_plane.upsert_config(
            key=ConfigKey(
                alternate_name=normalized_tenant,
                manufacturer="dataconv-tenant",
                sector=normalized_sector,
                manufacturer_version="v1",
                country=normalized_jurisdiction,
            ),
            content=content,
            updated_by=content["activatedBy"],
        )
        return {
            "active": True,
            "tenantId": normalized_tenant,
            "networkKind": network_kind,
            "jurisdiction": normalized_jurisdiction,
            "sector": normalized_sector,
            "controller": content["controller"],
            "credentialIds": content["credentialIds"],
            "revision": stored.revision,
        }
