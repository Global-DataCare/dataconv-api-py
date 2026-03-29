from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatchcase
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from typing import Any
import base64
import json
from threading import Lock
from time import time
from urllib.request import urlopen
import uuid

try:
    import jwt as pyjwt  # type: ignore[import-untyped]
    from jwt.algorithms import RSAAlgorithm  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional dependency in some runtimes
    pyjwt = None  # type: ignore[assignment]
    RSAAlgorithm = None  # type: ignore[assignment]


_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_JWKS_CACHE_LOCK = Lock()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    text = str(raw or "").strip()
    if not text:
        return b""
    padding = "=" * ((4 - len(text) % 4) % 4)
    return base64.urlsafe_b64decode(f"{text}{padding}")


def _jwt_parts(token: str) -> tuple[str, str, str]:
    text = str(token or "").strip()
    parts = text.split(".")
    if len(parts) != 3:
        raise ValueError("JWT must have exactly 3 parts")
    return parts[0], parts[1], parts[2]


def parse_jwt_unverified(token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    header_b64, payload_b64, _ = _jwt_parts(token)
    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise ValueError("Invalid JWT encoding") from exc
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise ValueError("JWT header/payload must be JSON objects")
    return header, payload


def normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def hash_email_same_as(email: str) -> str:
    normalized = normalize_email(email)
    if not normalized:
        return ""
    return sha256(normalized.encode("utf-8")).hexdigest().lower()


def email_hash_matches(email_hash: str, expected_hash: str) -> bool:
    left = str(email_hash or "").strip().lower()
    right_raw = str(expected_hash or "").strip().lower()
    if not left or not right_raw:
        return False
    right = right_raw
    for prefix in ("sha256:", "sha-256:", "urn:sha256:"):
        if right.startswith(prefix):
            right = right[len(prefix) :]
            break
    return compare_digest(left, right)


def _as_str_set(value: Any) -> set[str]:
    if isinstance(value, str):
        items = [item.strip() for item in value.split(" ") if item.strip()]
        return {item for item in items if item}
    if isinstance(value, list):
        out: set[str] = set()
        for item in value:
            if isinstance(item, str) and item.strip():
                out.add(item.strip())
        return out
    return set()


def _scope_pattern_matches(required_scope: str, allowed_scope_pattern: str) -> bool:
    required = str(required_scope or "").strip()
    pattern = str(allowed_scope_pattern or "").strip()
    if not required or not pattern:
        return False
    if pattern == "*":
        return True
    if "*" in pattern:
        return fnmatchcase(required, pattern)
    return required == pattern


def _as_epoch(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _aud_matches(payload_aud: Any, expected: str) -> bool:
    target = str(expected or "").strip()
    if not target:
        return True
    if isinstance(payload_aud, str):
        return payload_aud.strip() == target
    if isinstance(payload_aud, list):
        return any(str(item).strip() == target for item in payload_aud)
    return False


def _temporal_claims_valid(payload: dict[str, Any], *, now_epoch: int, skew_seconds: int = 60) -> bool:
    exp = _as_epoch(payload.get("exp"), 0)
    if exp <= 0:
        return False
    if exp < (now_epoch - skew_seconds):
        return False
    nbf = _as_epoch(payload.get("nbf"), 0)
    if nbf and nbf > (now_epoch + skew_seconds):
        return False
    iat = _as_epoch(payload.get("iat"), 0)
    if iat and iat > (now_epoch + skew_seconds):
        return False
    return True


def _verify_signature_placeholder(token: str, *, allow_insecure: bool, demo_mode: bool = False) -> None:
    if demo_mode:
        return  # Skip signature verification in demo mode
    header, _ = parse_jwt_unverified(token)
    alg = str(header.get("alg") or "").strip()
    if not alg:
        raise ValueError("JWT alg is missing")
    if alg.lower() == "none" and not allow_insecure:
        raise ValueError("Unsigned JWT is not allowed")


def _load_json_url(url: str, timeout_seconds: int = 5) -> dict[str, Any]:
    with urlopen(url, timeout=timeout_seconds) as response:  # nosec B310 - controlled issuer metadata URLs
        raw = response.read()
    decoded = json.loads(raw.decode("utf-8"))
    return decoded if isinstance(decoded, dict) else {}


def _normalize_issuer(raw_issuer: str) -> str:
    issuer = str(raw_issuer or "").strip()
    if issuer == "accounts.google.com":
        return "https://accounts.google.com"
    return issuer


def _issuer_allowed(issuer: str, allowed_patterns: tuple[str, ...]) -> bool:
    normalized = _normalize_issuer(issuer)
    for pattern in allowed_patterns:
        candidate = _normalize_issuer(pattern)
        if not candidate:
            continue
        if "*" in candidate:
            if fnmatchcase(normalized, candidate):
                return True
            continue
        if normalized == candidate:
            return True
    return False


def _resolve_jwks_uri_for_issuer(issuer: str) -> str:
    normalized = _normalize_issuer(issuer)
    if normalized in {"https://accounts.google.com"}:
        return "https://www.googleapis.com/oauth2/v3/certs"
    if normalized.startswith("https://login.microsoftonline.com/") and normalized.endswith("/v2.0"):
        return "https://login.microsoftonline.com/common/discovery/v2.0/keys"
    if normalized.startswith("https://securetoken.google.com/"):
        return "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"

    issuer_base = normalized.rstrip("/")
    openid = _load_json_url(f"{issuer_base}/.well-known/openid-configuration")
    jwks_uri = str(openid.get("jwks_uri") or "").strip()
    if not jwks_uri:
        raise ValueError("Unable to resolve OIDC jwks_uri for issuer")
    return jwks_uri


def _load_jwks_cached(jwks_uri: str, ttl_seconds: int) -> dict[str, Any]:
    now_ts = float(time())
    with _JWKS_CACHE_LOCK:
        cached = _JWKS_CACHE.get(jwks_uri)
        if cached and cached[0] > now_ts:
            return cached[1]
    jwks = _load_json_url(jwks_uri)
    expires_at = now_ts + max(1, int(ttl_seconds or 1))
    with _JWKS_CACHE_LOCK:
        _JWKS_CACHE[jwks_uri] = (expires_at, jwks)
    return jwks


def _verify_oidc_jwt(token: str, settings: Any) -> dict[str, Any]:
    if pyjwt is None or RSAAlgorithm is None:
        raise ValueError("OIDC JWT validation requires pyjwt[crypto] dependency")

    header, payload = parse_jwt_unverified(token)
    algorithm = str(header.get("alg") or "").strip()
    if not algorithm:
        raise ValueError("JWT alg is missing")
    if algorithm.lower() == "none":
        raise ValueError("Unsigned JWT is not allowed in secure mode")

    issuer = str(payload.get("iss") or "").strip()
    if not issuer:
        raise ValueError("id_token missing iss claim")

    configured_patterns = tuple(
        str(item or "").strip()
        for item in getattr(settings, "exchange_oidc_allowed_issuers", ())
        if str(item or "").strip()
    )
    if not configured_patterns:
        single_issuer = str(getattr(settings, "exchange_oidc_issuer", "") or "").strip()
        if single_issuer:
            configured_patterns = (single_issuer,)
        else:
            configured_patterns = (
                "https://accounts.google.com",
                "accounts.google.com",
                "https://login.microsoftonline.com/*/v2.0",
                "https://securetoken.google.com/*",
            )
    if not _issuer_allowed(issuer, configured_patterns):
        raise ValueError("id_token issuer mismatch")

    configured_audiences = tuple(
        str(item or "").strip()
        for item in getattr(settings, "exchange_oidc_allowed_audiences", ())
        if str(item or "").strip()
    )
    if not configured_audiences:
        single_audience = str(getattr(settings, "exchange_oidc_audience", "") or "").strip()
        if single_audience:
            configured_audiences = (single_audience,)

    jwks_uri = _resolve_jwks_uri_for_issuer(issuer)
    jwks = _load_jwks_cached(
        jwks_uri,
        ttl_seconds=int(getattr(settings, "exchange_oidc_jwks_cache_ttl_seconds", 3600) or 3600),
    )
    keys = jwks.get("keys") if isinstance(jwks.get("keys"), list) else []
    kid = str(header.get("kid") or "").strip()
    selected_jwk: dict[str, Any] | None = None
    for key in keys:
        if not isinstance(key, dict):
            continue
        if kid and str(key.get("kid") or "").strip() != kid:
            continue
        selected_jwk = key
        break
    if selected_jwk is None:
        raise ValueError("Unable to find signing key for id_token")

    public_key = RSAAlgorithm.from_jwk(json.dumps(selected_jwk, separators=(",", ":")))
    decode_kwargs: dict[str, Any] = {
        "algorithms": [algorithm],
        "issuer": _normalize_issuer(issuer),
        "options": {
            "verify_signature": True,
            "verify_exp": True,
            "verify_iat": True,
            "verify_nbf": True,
            "verify_iss": True,
            "verify_aud": bool(configured_audiences),
        },
        "leeway": 60,
    }
    if configured_audiences:
        decode_kwargs["audience"] = list(configured_audiences)
    decoded = pyjwt.decode(token, key=public_key, **decode_kwargs)
    if not isinstance(decoded, dict):
        raise ValueError("id_token payload is invalid")
    return decoded


@dataclass(frozen=True)
class ValidatedIdToken:
    issuer: str
    subject: str
    email: str
    email_hash: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ParsedVp:
    holder: str
    holder_key: str
    vp_jti: str
    operational_subject: str
    organization: str
    same_as_hash: str
    scopes: set[str]
    payload: dict[str, Any]


@dataclass(frozen=True)
class ValidatedClientAssertion:
    issuer: str
    subject: str
    holder_key: str
    jti: str
    vp_jti: str
    payload: dict[str, Any]


def validate_id_token(id_token: str, settings: Any) -> ValidatedIdToken:
    demo_mode = bool(getattr(settings, "demo_mode", False))
    allow_insecure = bool(getattr(settings, "exchange_allow_insecure_assertions", True))
    _verify_signature_placeholder(id_token, allow_insecure=allow_insecure, demo_mode=demo_mode)
    _, payload = parse_jwt_unverified(id_token)
    
    if not demo_mode:
        header_alg = str(parse_jwt_unverified(id_token)[0].get("alg") or "").strip().lower()
        if header_alg == "none" and allow_insecure:
            now_epoch = int(datetime.now(tz=timezone.utc).timestamp())
            if not _temporal_claims_valid(payload, now_epoch=now_epoch):
                raise ValueError("id_token temporal claims are invalid")

            expected_issuer = str(getattr(settings, "exchange_oidc_issuer", "") or "").strip()
            issuer = str(payload.get("iss") or "").strip()
            if expected_issuer and _normalize_issuer(issuer) != _normalize_issuer(expected_issuer):
                raise ValueError("id_token issuer mismatch")

            expected_audience = str(getattr(settings, "exchange_oidc_audience", "") or "").strip()
            if expected_audience and not _aud_matches(payload.get("aud"), expected_audience):
                raise ValueError("id_token audience mismatch")
        else:
            payload = _verify_oidc_jwt(id_token, settings)

    email = normalize_email(
        str(payload.get("email") or payload.get("preferred_username") or payload.get("upn") or "")
    )
    if not email:
        raise ValueError("id_token missing email claim")

    subject = str(payload.get("sub") or email).strip()
    return ValidatedIdToken(
        issuer=str(payload.get("iss") or "").strip(),
        subject=subject,
        email=email,
        email_hash=hash_email_same_as(email),
        payload=payload,
    )


def _extract_vc_payload(vc_raw: Any) -> dict[str, Any]:
    if isinstance(vc_raw, dict):
        return vc_raw
    if isinstance(vc_raw, str) and vc_raw.count(".") == 2:
        _, vc_payload = parse_jwt_unverified(vc_raw)
        return vc_payload
    return {}


def parse_and_validate_vp_token(vp_token: str, settings: Any) -> ParsedVp:
    demo_mode = bool(getattr(settings, "demo_mode", False))
    allow_insecure = bool(getattr(settings, "exchange_allow_insecure_assertions", True))
    _verify_signature_placeholder(vp_token, allow_insecure=allow_insecure, demo_mode=demo_mode)
    header, payload = parse_jwt_unverified(vp_token)

    holder = str(payload.get("holder") or payload.get("sub") or payload.get("iss") or "").strip()
    vp = payload.get("vp") if isinstance(payload.get("vp"), dict) else {}
    if not holder and isinstance(vp, dict):
        holder = str(vp.get("holder") or "").strip()
    if not holder:
        raise ValueError("vp_token missing holder/sub/iss")

    vc_list = []
    if isinstance(vp, dict):
        vc_raw = vp.get("verifiableCredential")
        if isinstance(vc_raw, list):
            vc_list = vc_raw
        elif vc_raw is not None:
            vc_list = [vc_raw]
    if not vc_list and payload.get("verifiableCredential") is not None:
        vc_raw_root = payload.get("verifiableCredential")
        if isinstance(vc_raw_root, list):
            vc_list = vc_raw_root
        else:
            vc_list = [vc_raw_root]

    vc_payload = _extract_vc_payload(vc_list[0] if vc_list else {})
    credential_subject = vc_payload.get("credentialSubject")
    if not isinstance(credential_subject, dict):
        credential_subject = {}

    same_as = str(
        credential_subject.get("sameAs")
        or credential_subject.get("same_as")
        or ""
    ).strip().lower()
    if not same_as:
        raise ValueError("VC credentialSubject.sameAs is required")

    operational_subject = str(credential_subject.get("id") or "").strip()
    if not operational_subject:
        raise ValueError("VC credentialSubject.id is required")

    organization = str(
        credential_subject.get("organization")
        or credential_subject.get("organizationId")
        or credential_subject.get("tenantId")
        or credential_subject.get("taxID")
        or credential_subject.get("taxId")
        or ""
    ).strip()

    scopes = _as_str_set(credential_subject.get("scope")) | _as_str_set(credential_subject.get("scopes"))
    holder_key = str(header.get("kid") or "").strip()
    if not holder_key and isinstance(payload.get("cnf"), dict):
        holder_key = str((payload.get("cnf") or {}).get("kid") or "").strip()

    return ParsedVp(
        holder=holder,
        holder_key=holder_key,
        vp_jti=str(payload.get("jti") or "").strip(),
        operational_subject=operational_subject,
        organization=organization,
        same_as_hash=same_as,
        scopes=scopes,
        payload=payload,
    )


def validate_client_assertion(
    client_assertion: str,
    *,
    expected_audience: str,
    settings: Any,
    replay_cache: dict[str, int],
) -> ValidatedClientAssertion:
    demo_mode = bool(getattr(settings, "demo_mode", False))
    allow_insecure = bool(getattr(settings, "exchange_allow_insecure_assertions", True))
    _verify_signature_placeholder(client_assertion, allow_insecure=allow_insecure, demo_mode=demo_mode)
    header, payload = parse_jwt_unverified(client_assertion)
    
    if not demo_mode:
        now_epoch = int(datetime.now(tz=timezone.utc).timestamp())
        if not _temporal_claims_valid(payload, now_epoch=now_epoch):
            raise ValueError("client_assertion temporal claims are invalid")
        if not _aud_matches(payload.get("aud"), expected_audience):
            raise ValueError("client_assertion audience mismatch")

        jti = str(payload.get("jti") or "").strip()
        if not jti:
            raise ValueError("client_assertion jti is required")
        used_exp = _as_epoch(payload.get("exp"), now_epoch + 1)
        for cache_jti, cache_exp in list(replay_cache.items()):
            if cache_exp <= now_epoch:
                replay_cache.pop(cache_jti, None)
        if jti in replay_cache:
            raise ValueError("client_assertion replay detected")
        replay_cache[jti] = used_exp
    else:
        jti = str(payload.get("jti") or "").strip()

    issuer = str(payload.get("iss") or "").strip()
    subject = str(payload.get("sub") or issuer).strip()
    holder_key = str(header.get("kid") or "").strip()
    if not holder_key and isinstance(payload.get("cnf"), dict):
        holder_key = str((payload.get("cnf") or {}).get("kid") or "").strip()
    return ValidatedClientAssertion(
        issuer=issuer,
        subject=subject,
        holder_key=holder_key,
        jti=jti,
        vp_jti=str(payload.get("vp_jti") or "").strip(),
        payload=payload,
    )


def ensure_vp_client_binding(vp: ParsedVp, assertion: ValidatedClientAssertion) -> None:
    if vp.holder_key and assertion.holder_key and vp.holder_key != assertion.holder_key:
        raise ValueError("client_assertion and vp_token key binding mismatch")
    holder_candidates = {value for value in (vp.holder, assertion.issuer, assertion.subject) if value}
    if len(holder_candidates) > 1:
        raise ValueError("client_assertion and vp_token holder mismatch")
    if assertion.vp_jti and vp.vp_jti and assertion.vp_jti != vp.vp_jti:
        raise ValueError("client_assertion vp_jti mismatch")


def validate_requested_scopes(requested_scope: str, vp_scopes: set[str], settings: Any) -> list[str]:
    demo_mode = bool(getattr(settings, "demo_mode", False))
    requested = [part.strip() for part in str(requested_scope or "").split(" ") if part.strip()]
    if not requested:
        requested = ["dataconv.upload"]

    if demo_mode:
        return requested  # Allow any requested scope in demo mode

    configured_default = str(getattr(settings, "exchange_default_allowed_scopes", "") or "").strip()
    configured_set = {item for item in configured_default.split(" ") if item}
    allowed = set(vp_scopes) if vp_scopes else set(configured_set)
    if not allowed:
        allowed = {"dataconv.upload"}

    for scope in requested:
        if not any(_scope_pattern_matches(scope, allowed_scope) for allowed_scope in allowed):
            raise ValueError(f"requested scope not allowed by VC: {scope}")
    return requested


def _jwt_sign_hs256(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_raw = json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    header_b64 = _b64url_encode(header_raw)
    payload_b64 = _b64url_encode(payload_raw)
    signed_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac_new(secret.encode("utf-8"), signed_input, "sha256").digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def _verify_hs256_signature(token: str, secret: str) -> bool:
    header_b64, payload_b64, sig_b64 = _jwt_parts(token)
    signed_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac_new(secret.encode("utf-8"), signed_input, "sha256").digest()
    actual = _b64url_decode(sig_b64)
    return compare_digest(expected, actual)


def issue_session_access_token(
    *,
    subject: str,
    organization: str,
    scopes: list[str],
    settings: Any,
) -> tuple[str, int, dict[str, Any]]:
    now = datetime.now(tz=timezone.utc)
    ttl_seconds = int(getattr(settings, "exchange_session_token_ttl_seconds", 900) or 900)
    exp = now + timedelta(seconds=ttl_seconds)
    payload = {
        "iss": str(getattr(settings, "default_issuer_did", "did:web:globaldatacare.es:employee:preconversion") or "").strip(),
        "sub": str(subject or "").strip(),
        "aud": str(getattr(settings, "default_audience_did", "did:web:globaldatacare.es") or "").strip(),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": str(uuid.uuid4()),
        "token_use": "dataconv_access",
        "organization": str(organization or "").strip(),
        "scope": " ".join(scopes),
        "scopes": scopes,
    }
    secret = str(getattr(settings, "exchange_session_token_secret", "") or "").strip()
    if not secret:
        raise ValueError("Session token secret is not configured")
    token = _jwt_sign_hs256(payload, secret)
    return token, ttl_seconds, payload


def validate_session_access_token(token: str, settings: Any) -> dict[str, Any]:
    demo_mode = bool(getattr(settings, "demo_mode", False))
    header, payload = parse_jwt_unverified(token)
    
    if not demo_mode:
        alg = str(header.get("alg") or "").strip().upper()
        secret = str(getattr(settings, "exchange_session_token_secret", "") or "").strip()
        if alg == "HS256":
            if not secret or not _verify_hs256_signature(token, secret):
                raise ValueError("Invalid session token signature")
        else:
            allow_insecure = bool(getattr(settings, "exchange_allow_insecure_assertions", True))
            if not allow_insecure:
                raise ValueError("Unsupported session token algorithm")

        now_epoch = int(datetime.now(tz=timezone.utc).timestamp())
        if not _temporal_claims_valid(payload, now_epoch=now_epoch):
            raise ValueError("Session token expired or invalid")
    
    if str(payload.get("token_use") or "") != "dataconv_access":
        raise ValueError("Invalid session token use")
    return payload
