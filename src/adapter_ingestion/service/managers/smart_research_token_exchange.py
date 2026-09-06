# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
import json
from time import monotonic, time
from typing import Any, Callable
from urllib.parse import unquote, urlparse
from urllib.request import urlopen

try:
    import jwt  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - production profile installs PyJWT[crypto]
    jwt = None  # type: ignore[assignment]

from ..auth_exchange import issue_session_access_token, parse_jwt_unverified
from ..research_study import normalize_research_study_reference


SMART_ACCESS_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"
SMART_RESEARCH_PURPOSE = "HRESCH"
DATACONV_RESEARCH_SCOPES = ["dataconv.upload", "dataconv.read", "dataconv.review"]


@dataclass(frozen=True)
class SmartResearchTokenExchangeResult:
    access_token: str
    token_type: str
    expires_in: int
    scope: str
    granted_scopes: list[str]
    subject: str
    organization: str
    study: str


def did_web_document_url(issuer: str, *, demo_mode: bool) -> str:
    """Resolve a did:web identifier according to the DID Web path mapping."""
    value = str(issuer or "").strip()
    prefix = "did:web:"
    if not value.startswith(prefix):
        raise ValueError("SMART issuer must be a did:web identifier")
    method_specific = value[len(prefix):]
    parts = method_specific.split(":")
    authority = unquote(parts[0]) if parts else ""
    if not authority or any(character in authority for character in "/?#@"):
        raise ValueError("SMART issuer did:web authority is invalid")
    decoded_path_parts = [unquote(part) for part in parts[1:] if part]
    if any(any(character in part for character in "/?#") for part in decoded_path_parts):
        raise ValueError("SMART issuer did:web path is invalid")
    path = "/".join(decoded_path_parts)
    local_authority = authority.split(":", 1)[0].lower() in {"localhost", "127.0.0.1", "::1"}
    if local_authority:
        if not demo_mode:
            raise ValueError("SMART issuer DID document requires HTTPS outside demo/test mode")
        scheme = "http"
    else:
        scheme = "https"
    suffix = f"/{path}/did.json" if path else "/.well-known/did.json"
    return f"{scheme}://{authority}{suffix}"


def _load_did_document(url: str, timeout_seconds: int) -> dict[str, Any]:
    with urlopen(url, timeout=timeout_seconds) as response:  # nosec B310 - URL derives from an allowlisted did:web issuer
        final_url = str(response.geturl() or url)
        if urlparse(url).scheme == "https" and urlparse(final_url).scheme != "https":
            raise ValueError("SMART issuer DID document redirected outside HTTPS")
        document = json.loads(response.read().decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("SMART issuer DID document is invalid")
    return document


def _allowed(value: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern and fnmatchcase(value, pattern) for pattern in patterns)


class SmartResearchTokenExchangeManager:
    """Validate one GW SMART JWT offline and mint a study-pinned DataConv JWT."""

    def __init__(
        self,
        settings: Any,
        *,
        did_document_loader: Callable[[str, int], dict[str, Any]] = _load_did_document,
        tenant_is_active: Callable[[str, str, str], bool] | None = None,
    ) -> None:
        self._settings = settings
        self._did_document_loader = did_document_loader
        self._tenant_is_active = tenant_is_active or (lambda _tenant, _jurisdiction, _sector: True)
        self._did_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def _resolve_did_document(self, url: str) -> dict[str, Any]:
        now = monotonic()
        cached = self._did_cache.get(url)
        if cached is not None and cached[0] > now:
            return cached[1]
        try:
            document = self._did_document_loader(
                url,
                int(getattr(self._settings, "smart_gw_http_timeout_seconds", 5) or 5),
            )
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("SMART issuer DID document resolution failed") from exc
        if not isinstance(document, dict):
            raise ValueError("SMART issuer DID document is invalid")
        ttl = max(0, int(getattr(self._settings, "smart_gw_did_cache_ttl_seconds", 300) or 300))
        if ttl:
            self._did_cache[url] = (now + ttl, document)
        return document

    def _validate(self, token: str, *, tenant_id: str) -> dict[str, Any]:
        if jwt is None:
            raise ValueError("SMART JWT validation requires PyJWT[crypto]")
        header, unverified = parse_jwt_unverified(token)
        issuer = str(unverified.get("iss") or "").strip()
        patterns = tuple(
            str(item or "").strip()
            for item in getattr(self._settings, "smart_gw_allowed_issuers", ())
            if str(item or "").strip()
        )
        if not patterns or not _allowed(issuer, patterns):
            raise ValueError("SMART issuer is not explicitly allowed")

        bindings = getattr(self._settings, "smart_gw_issuer_tenant_bindings", {})
        expected_tenant = str(bindings.get(issuer) or "").strip() if isinstance(bindings, dict) else ""
        if not expected_tenant or expected_tenant.lower() != str(tenant_id or "").strip().lower():
            raise ValueError("SMART issuer is not bound to the requested tenant")

        demo_mode = bool(getattr(self._settings, "demo_mode", False)) or str(
            getattr(self._settings, "network_mode", "") or ""
        ).strip().lower() == "test"
        document_url = did_web_document_url(issuer, demo_mode=demo_mode)
        document = self._resolve_did_document(document_url)
        if str(document.get("id") or "").strip() != issuer:
            raise ValueError("SMART issuer DID document id mismatch")

        key_id = str(header.get("kid") or "").strip()
        if not key_id:
            raise ValueError("SMART JWT kid is required")
        authentication_ids = {
            str(item.get("id") if isinstance(item, dict) else item or "").strip()
            for item in document.get("authentication", [])
        }
        methods = document.get("verificationMethod", [])
        matching_methods: list[dict[str, Any]] = []
        for item in methods if isinstance(methods, list) else []:
            if not isinstance(item, dict):
                continue
            candidate_jwk = item.get("publicKeyJwk") if isinstance(item.get("publicKeyJwk"), dict) else {}
            if (
                str(item.get("id") or "").strip() == key_id
                or str(candidate_jwk.get("kid") or "").strip() == key_id
            ):
                matching_methods.append(item)
        if len(matching_methods) != 1:
            raise ValueError("SMART JWT kid must resolve to one DID verification method")
        method = matching_methods[0]
        method_id = str(method.get("id") or "").strip() if method is not None else ""
        if method_id not in authentication_ids:
            raise ValueError("SMART JWT signing key is not a DID authentication method")
        jwk = method.get("publicKeyJwk") if isinstance(method.get("publicKeyJwk"), dict) else {}
        if str(method.get("controller") or "").strip() != issuer or str(jwk.get("use") or "sig").strip() != "sig":
            raise ValueError("SMART JWT signing key is not controlled by the issuer for signatures")
        algorithm = str(jwk.get("alg") or "").strip()
        if not algorithm or str(header.get("alg") or "").strip() != algorithm:
            raise ValueError("SMART JWT algorithm does not match DID publicKeyJwk.alg")

        expected_audiences = tuple(
            str(item or "").strip()
            for item in getattr(self._settings, "smart_gw_expected_audiences", ())
            if str(item or "").strip()
        )
        if not expected_audiences or issuer not in expected_audiences:
            raise ValueError("SMART audience is not explicitly configured")
        try:
            decoded = jwt.decode(
                token,
                key=jwt.PyJWK.from_dict(jwk).key,
                algorithms=[algorithm],
                audience=issuer,
                issuer=issuer,
                options={"require": ["iss", "sub", "aud", "scope", "purpose", "study", "exp", "nbf"]},
                leeway=60,
            )
        except jwt.ExpiredSignatureError as exc:
            raise ValueError("SMART access token expired") from exc
        except jwt.InvalidSignatureError as exc:
            raise ValueError("SMART access token signature is invalid") from exc
        except Exception as exc:
            raise ValueError(f"SMART access token validation failed: {exc}") from exc

        subject = str(decoded.get("sub") or "").strip()
        if not subject.startswith("did:") or subject == issuer:
            raise ValueError("SMART subject must identify the authorized professional")
        purpose = str(decoded.get("purpose") or "").strip()
        if purpose != SMART_RESEARCH_PURPOSE:
            raise ValueError("SMART purpose must be HRESCH")
        raw_study = str(decoded.get("study") or "").strip()
        if not raw_study.startswith("ResearchStudy/"):
            raise ValueError("SMART study must be a relative ResearchStudy reference")
        study = normalize_research_study_reference(raw_study)
        expected_scope = f"organization/ResearchSubject.crus?study={study}"
        if str(decoded.get("scope") or "").strip() != expected_scope:
            raise ValueError("SMART scope must grant exact ResearchSubject crus for the same study")
        return decoded

    def exchange(
        self,
        payload: dict[str, Any],
        *,
        tenant_id: str,
        jurisdiction: str,
        sector: str,
    ) -> SmartResearchTokenExchangeResult:
        request = payload if isinstance(payload, dict) else {}
        unexpected = sorted(set(request) - {"subject_token", "subject_token_type"})
        if unexpected:
            raise ValueError(f"unexpected professional research exchange field: {unexpected[0]}")
        token_type = str(request.get("subject_token_type") or "").strip()
        if token_type != SMART_ACCESS_TOKEN_TYPE:
            raise ValueError(f"subject_token_type must be {SMART_ACCESS_TOKEN_TYPE}")
        subject_token = str(request.get("subject_token") or "").strip()
        if not subject_token:
            raise ValueError("subject_token is required")
        if not self._tenant_is_active(tenant_id, jurisdiction, sector):
            raise PermissionError("DataConv tenant is not active for this network, sector and jurisdiction")
        claims = self._validate(subject_token, tenant_id=tenant_id)
        subject = str(claims["sub"])
        study = str(claims["study"])
        access_token, expires_in, _ = issue_session_access_token(
            subject=subject,
            organization=tenant_id,
            scopes=list(DATACONV_RESEARCH_SCOPES),
            settings=self._settings,
            additional_claims={
                "actor": subject,
                "study": study,
                "purpose": SMART_RESEARCH_PURPOSE,
                "token_profile": "professional_research",
            },
            ttl_seconds_override=max(1, int(claims["exp"]) - int(time())),
        )
        return SmartResearchTokenExchangeResult(
            access_token=access_token,
            token_type="Bearer",
            expires_in=expires_in,
            scope=" ".join(DATACONV_RESEARCH_SCOPES),
            granted_scopes=list(DATACONV_RESEARCH_SCOPES),
            subject=subject,
            organization=str(tenant_id or "").strip(),
            study=study,
        )

    @staticmethod
    def as_response(result: SmartResearchTokenExchangeResult) -> dict[str, Any]:
        return {
            "access_token": result.access_token,
            "issued_token_type": SMART_ACCESS_TOKEN_TYPE,
            "token_type": result.token_type,
            "expires_in": result.expires_in,
            "scope": result.scope,
            "subject": result.subject,
            "organization": result.organization,
            "study": result.study,
        }
