from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..auth_exchange import (
    email_hash_matches,
    ensure_vp_client_binding,
    issue_session_access_token,
    parse_and_validate_vp_token,
    validate_client_assertion,
    validate_id_token,
    validate_requested_scopes,
)
from .tenant_api_keys import TenantApiKeyManager


@dataclass
class TokenExchangeResult:
    access_token: str
    token_type: str
    expires_in: int
    scope: str
    granted_scopes: list[str]
    subject: str
    organization: str


class TokenExchangeManager:
    def __init__(self, settings: Any, *, tenant_api_key_manager: TenantApiKeyManager | None = None) -> None:
        self._settings = settings
        self._replay_cache: dict[str, int] = {}
        self._tenant_api_key_manager = tenant_api_key_manager

    @staticmethod
    def _parse_scope(raw_scope: Any) -> str:
        return str(raw_scope or "").strip()

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def exchange(self, payload: dict[str, Any], *, audience: str) -> TokenExchangeResult:
        request = self._as_dict(payload)
        subject_token = str(request.get("subject_token") or "").strip()
        subject_token_type = str(request.get("subject_token_type") or "").strip()
        vp_token = str(request.get("vp_token") or "").strip()
        client_assertion = str(request.get("client_assertion") or "").strip()
        client_assertion_type = str(request.get("client_assertion_type") or "").strip()
        api_key = str(request.get("api_key") or "").strip()
        api_key_profile = str(request.get("api_key_profile") or request.get("auth_profile") or "").strip().lower()
        requested_scope = self._parse_scope(request.get("scope"))
        api_key_exception_requested = api_key_profile == "api-key-exception.v1"
        api_key_exception_enabled = bool(getattr(self._settings, "exchange_allow_api_key_exception", False))

        if api_key_exception_requested and not api_key:
            raise ValueError("api_key is required for api-key-exception.v1")
        if (
            api_key
            and not subject_token
            and not api_key_exception_requested
        ):
            raise ValueError("subject_token is required unless api_key_profile=api-key-exception.v1")
        if api_key_exception_requested and not api_key_exception_enabled:
            raise ValueError("api-key-exception.v1 is not enabled")
        if subject_token:
            if subject_token_type != "urn:ietf:params:oauth:token-type:id_token":
                raise ValueError("subject_token_type must be urn:ietf:params:oauth:token-type:id_token")
        elif not (api_key and api_key_exception_requested and api_key_exception_enabled):
            raise ValueError("subject_token is required")

        # TODO(ica-clearing-house): before issuing an access token, call the ICA clearing-house
        # endpoint (`/clearinghouse/verify` on the configured ICA base URL) to validate that the
        # presenter's DID/credential has not been revoked and is authorised for this dataspace.
        # The call should happen here, after parsing id_token but before resolving scopes or
        # issuing the session token. Blocked on: ICA clearing-house endpoint being available and
        # the PRECONV_ICA_BASE_URL / PRECONV_ICA_API_KEY settings being agreed.
        id_token = validate_id_token(subject_token, self._settings) if subject_token else None
        if api_key:
            tenant_id = str(request.get("organization") or "").strip().lower()
            tenant_policy = None
            if self._tenant_api_key_manager is not None and tenant_id:
                if id_token is not None:
                    tenant_policy = self._tenant_api_key_manager.resolve_policy(
                        tenant_id=tenant_id,
                        api_key=api_key,
                        email=id_token.email,
                    )
                elif api_key_exception_requested and api_key_exception_enabled:
                    tenant_policy = self._tenant_api_key_manager.resolve_policy_without_email(
                        tenant_id=tenant_id,
                        api_key=api_key,
                    )

            if tenant_policy is not None:
                granted_scopes = validate_requested_scopes(requested_scope, set(tenant_policy.scopes), self._settings)
                operational_subject = (
                    str(request.get("operational_subject") or "").strip()
                    or tenant_policy.operational_subject
                    or str(getattr(self._settings, "exchange_api_key_subject_default", "") or "").strip()
                    or (id_token.subject if id_token is not None else "")
                )
                organization = tenant_policy.tenant_id
            else:
                allow_api_key = bool(getattr(self._settings, "exchange_allow_api_key", False))
                configured_api_keys = {
                    str(item or "").strip().lower()
                    for item in getattr(self._settings, "exchange_api_keys", ())
                    if str(item or "").strip()
                }
                if not allow_api_key:
                    raise ValueError("api_key is not enabled for exchange")
                if not configured_api_keys or str(api_key).lower() not in configured_api_keys:
                    raise ValueError("invalid api_key")

                granted_scopes = validate_requested_scopes(requested_scope, set(), self._settings)
                operational_subject = (
                    str(request.get("operational_subject") or "").strip()
                    or str(getattr(self._settings, "exchange_api_key_subject_default", "") or "").strip()
                    or (id_token.subject if id_token is not None else "")
                )
                organization = (
                    str(request.get("organization") or "").strip()
                    or str(getattr(self._settings, "exchange_api_key_org_default", "") or "").strip()
                )
            if not operational_subject:
                raise ValueError("operational_subject is required for api_key exchange")
            if not organization:
                raise ValueError("organization is required for api_key exchange")
        else:
            if client_assertion_type != "urn:ietf:params:oauth:client-assertion-type:jwt-bearer":
                raise ValueError("client_assertion_type must be urn:ietf:params:oauth:client-assertion-type:jwt-bearer")
            if not vp_token:
                raise ValueError("vp_token is required")
            if not client_assertion:
                raise ValueError("client_assertion is required")
            if id_token is None:
                raise ValueError("subject_token is required")

            vp = parse_and_validate_vp_token(vp_token, self._settings)
            if not email_hash_matches(id_token.email_hash, vp.same_as_hash):
                raise ValueError("id_token email hash does not match VC credentialSubject.sameAs")

            assertion = validate_client_assertion(
                client_assertion,
                expected_audience=audience,
                settings=self._settings,
                replay_cache=self._replay_cache,
            )
            ensure_vp_client_binding(vp, assertion)
            granted_scopes = validate_requested_scopes(requested_scope, vp.scopes, self._settings)
            operational_subject = vp.operational_subject
            organization = vp.organization

        token, expires_in, _ = issue_session_access_token(
            subject=operational_subject,
            organization=organization,
            scopes=granted_scopes,
            settings=self._settings,
        )
        return TokenExchangeResult(
            access_token=token,
            token_type="Bearer",
            expires_in=expires_in,
            scope=" ".join(granted_scopes),
            granted_scopes=granted_scopes,
            subject=operational_subject,
            organization=organization,
        )

    @staticmethod
    def as_response(result: TokenExchangeResult) -> dict[str, Any]:
        now = datetime.now(tz=timezone.utc)
        return {
            "access_token": result.access_token,
            "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "token_type": result.token_type,
            "expires_in": result.expires_in,
            "scope": result.scope,
            "subject": result.subject,
            "organization": result.organization,
            "issued_at": int(now.timestamp()),
        }
