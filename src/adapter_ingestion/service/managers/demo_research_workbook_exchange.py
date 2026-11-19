# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import re
from time import time
from typing import Any, Callable

from ..auth_exchange import issue_session_access_token
from ..research_study import DEMO_RESEARCH_TOKEN_PROFILE, sector_requires_research_study
from .smart_research_token_exchange import (
    DATACONV_REVIEWER_SCOPES,
    SMART_RESEARCH_PURPOSE,
    SmartResearchTokenExchangeResult,
    jwt,
)

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
_MAX_ASSERTION_SECONDS = 90


class DemoResearchWorkbookExchangeManager:
    """Exchange a short-lived assertion from the BFF that owns Demo Consent."""

    def __init__(self, settings: Any, *, tenant_is_active: Callable[[str, str, str], bool]) -> None:
        self._settings = settings
        self._tenant_is_active = tenant_is_active

    def exchange(
        self, assertion: str, *, tenant_id: str, jurisdiction: str, sector: str,
    ) -> SmartResearchTokenExchangeResult:
        settings = self._settings
        if settings.network_mode != "demo" or settings.demo_mode:
            raise PermissionError("Demo research exchange requires an isolated authenticated Demo service")
        if not sector_requires_research_study(sector):
            raise PermissionError("Demo research exchange requires a study-scoped DataConv sector")
        issuer = getattr(settings, "demo_research_assertion_issuer", "")
        audience = getattr(settings, "demo_research_assertion_audience", "")
        jwk_value = getattr(settings, "demo_research_assertion_public_jwk", "")
        if not issuer or not audience or not jwk_value or jwt is None:
            raise PermissionError("Demo research assertion trust is not configured")
        if len(str(getattr(settings, "exchange_session_token_secret", "") or "").strip()) < 32:
            raise PermissionError("Demo research session secret is not configured")
        if not isinstance(assertion, str) or not 0 < len(assertion) <= 6000:
            raise ValueError("Demo research assertion is invalid")
        try:
            public_jwk = json.loads(jwk_value)
            if public_jwk.get("kty") != "EC" or public_jwk.get("crv") != "P-256" or "d" in public_jwk:
                raise ValueError("Demo research verification requires a P-256 public key")
            claims = jwt.decode(
                assertion, jwt.PyJWK.from_dict(public_jwk).key, algorithms=["ES256"], audience=audience,
                issuer=issuer, options={"strict_aud": True, "require": ["sub", "iat", "nbf", "exp"]},
            )
        except (AttributeError, TypeError, ValueError, jwt.PyJWTError) as exc:
            raise ValueError("Demo research assertion signature or JWT claims are invalid") from exc
        if (claims.get("tenant"), claims.get("jurisdiction"), claims.get("sector")) != (tenant_id, jurisdiction, sector):
            raise ValueError("Demo research assertion does not match the tenant route")
        subject = str(claims["sub"])
        study = str(claims.get("study", ""))
        if (not re.fullmatch(rf"urn:uuid:{_UUID}", subject) or not re.fullmatch(rf"ResearchStudy/{_UUID}", study)
                or claims.get("purpose") != SMART_RESEARCH_PURPOSE):
            raise ValueError("Demo research assertion actor, study or purpose is invalid")
        issued_at, not_before, expires = (claims[name] for name in ("iat", "nbf", "exp"))
        if (not all(type(value) is int for value in (issued_at, not_before, expires))
                or not issued_at <= not_before < expires <= issued_at + _MAX_ASSERTION_SECONDS):
            raise ValueError("Demo research assertion lifetime is invalid")
        if not self._tenant_is_active(tenant_id, jurisdiction, sector):
            raise PermissionError("DataConv Demo tenant is not active for this sector and jurisdiction")
        scopes = [scope for scope in DATACONV_REVIEWER_SCOPES if not scope.startswith("dataconv.config.")]
        token, ttl, _ = issue_session_access_token(
            subject=subject, organization=tenant_id, scopes=scopes, settings=settings,
            additional_claims={"actor": subject, "study": study, "purpose": SMART_RESEARCH_PURPOSE,
                               "token_profile": DEMO_RESEARCH_TOKEN_PROFILE},
            ttl_seconds_override=max(1, expires - int(time())),
        )
        return SmartResearchTokenExchangeResult(token, "Bearer", ttl, " ".join(scopes), scopes, subject, tenant_id, study)
