from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatchcase
from hashlib import sha256, sha3_256
from secrets import token_urlsafe
from typing import Any
from uuid import uuid4

from ...runtime import ConfigKey
from ..api_support import HTTPException
from ..auth_exchange import normalize_email, validate_session_access_token
from .dependencies import ApiManagerDependencies


def hash_api_key(raw_api_key: str) -> str:
    token = str(raw_api_key or "").strip()
    if not token:
        return ""
    return sha256(token.encode("utf-8")).hexdigest().lower()


def build_consent_ref(*, tenant_id: str, email_hash: str, target: str, scopes: list[str], instrument: dict[str, Any]) -> str:
    normalized_scopes = sorted(str(scope or "").strip() for scope in (scopes or []) if str(scope or "").strip())
    digest_input = "|".join(
        [
            str(tenant_id or "").strip().lower(),
            str(email_hash or "").strip().lower(),
            str(target or "").strip(),
            "|".join(normalized_scopes),
            str(instrument or {}),
        ]
    )
    return f"urn:consent:api-key-rule:{sha256(digest_input.encode('utf-8')).hexdigest().lower()}"


def _b58btc_encode(raw: bytes) -> str:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    if not raw:
        return ""
    zeros = 0
    for byte in raw:
        if byte == 0:
            zeros += 1
        else:
            break
    value = int.from_bytes(raw, byteorder="big", signed=False)
    out: list[str] = []
    while value > 0:
        value, rem = divmod(value, 58)
        out.append(alphabet[rem])
    if zeros:
        out.extend(["1"] * zeros)
    if not out:
        out.append("1")
    out.reverse()
    return "".join(out)


def hash_email_same_as(email: str) -> str:
    normalized = normalize_email(email)
    if not normalized:
        return ""
    digest = sha3_256(normalized.encode("utf-8")).digest()
    multihash = bytes([0x16, len(digest)]) + digest
    return f"z{_b58btc_encode(multihash)}"


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso_utc(raw: str) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _scope_allowed(required_scope: str, granted_scope_pattern: str) -> bool:
    required = str(required_scope or "").strip()
    granted = str(granted_scope_pattern or "").strip()
    if not required or not granted:
        return False
    if granted == "*":
        return True
    if "*" in granted:
        return fnmatchcase(required, granted)
    return required == granted


def _contains_scope(required_scope: str, granted_patterns: list[str]) -> bool:
    return any(_scope_allowed(required_scope, item) for item in granted_patterns)


@dataclass(frozen=True)
class TenantApiKeyPolicy:
    key_id: str
    tenant_id: str
    email_hash: str
    scopes: list[str]
    operational_subject: str
    odrl: dict[str, Any]


class TenantApiKeyManager:
    def __init__(self, deps: ApiManagerDependencies) -> None:
        self._deps = deps

    @staticmethod
    def _registry_key(tenant_id: str) -> ConfigKey:
        return ConfigKey(
            alternate_name=str(tenant_id or "").strip().lower(),
            manufacturer="tenant-api-keys",
        )

    @staticmethod
    def _extract_claim_scopes(claims: dict[str, Any]) -> list[str]:
        scopes: set[str] = set()
        for item in str(claims.get("scope") or "").split(" "):
            token = str(item or "").strip()
            if token:
                scopes.add(token)
        raw_scopes = claims.get("scopes")
        if isinstance(raw_scopes, list):
            for item in raw_scopes:
                token = str(item or "").strip()
                if token:
                    scopes.add(token)
        return sorted(scopes)

    def _get_registry(self, tenant_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        resolved = self._deps.control_plane.resolve_config(self._registry_key(tenant_id))
        content = dict(resolved.content) if resolved and isinstance(resolved.content, dict) else {}
        entries = content.get("keys") if isinstance(content.get("keys"), list) else []
        return content, [item for item in entries if isinstance(item, dict)]

    @staticmethod
    def _normalize_tenant(tenant_id: str) -> str:
        return str(tenant_id or "").strip().lower()

    @staticmethod
    def _extract_action_identifier(action: dict[str, Any]) -> str:
        return str(action.get("identifier") or action.get("keyId") or "").strip()

    @staticmethod
    def _extract_agent_email(action: dict[str, Any]) -> str:
        agent = action.get("agent") if isinstance(action.get("agent"), dict) else {}
        return normalize_email(str(agent.get("email") or ""))

    @staticmethod
    def _response_entry_from_registry_item(item: dict[str, Any], *, removed: bool = False) -> dict[str, Any]:
        scopes = [
            str(scope or "").strip()
            for scope in (item.get("scopes") if isinstance(item.get("scopes"), list) else [])
            if str(scope or "").strip()
        ]
        instrument_raw = item.get("instrument")
        instrument = instrument_raw if isinstance(instrument_raw, dict) else {}
        response = {
            "resource": {
                "@context": "https://schema.org",
                "@type": "Person",
                "identifier": str(item.get("keyId") or "").strip(),
                "keyHash": str(item.get("keyHash") or "").strip(),
                "actionStatus": str(item.get("actionStatus") or "").strip() or "active",
                "agent": {
                    "sameAs": str(item.get("emailHash") or "").strip(),
                },
                "target": str(item.get("target") or "").strip(),
                "scope": scopes,
                "instrument": instrument,
                "consentRef": str(item.get("consentRef") or "").strip(),
                "consentModel": str(item.get("consentModel") or "").strip() or "one-rule-one-consent-one-odrl",
                "tenantId": str(item.get("tenantId") or "").strip(),
                "expiresAt": str(item.get("expiresAt") or "").strip(),
            }
        }
        if removed:
            response["resource"]["removed"] = True
        return response

    @staticmethod
    def _extract_scopes(action: dict[str, Any]) -> list[str]:
        scopes: list[str] = []
        raw_scope = action.get("scope")
        if isinstance(raw_scope, str):
            token = str(raw_scope).strip()
            if token:
                scopes.append(token)
        elif isinstance(raw_scope, list):
            scopes.extend([str(item).strip() for item in raw_scope if str(item).strip()])

        target = str(action.get("target") or "").strip()
        if target and target not in scopes:
            scopes.append(target)
        return scopes

    @staticmethod
    def _extract_actions(payload: dict[str, Any]) -> list[dict[str, Any]]:
        data_list = payload.get("data")
        if isinstance(data_list, list):
            actions: list[dict[str, Any]] = []
            for item in data_list:
                if not isinstance(item, dict):
                    continue
                resource = item.get("resource")
                if isinstance(resource, dict):
                    actions.append(resource)
            return actions

        legacy_email = normalize_email(str(payload.get("email") or ""))
        legacy_scopes = payload.get("scopes")
        if legacy_email and isinstance(legacy_scopes, list):
            return [
                {
                    "@context": "https://schema.org",
                    "@type": "UpdateAction",
                    "agent": {"email": legacy_email},
                    "scope": [str(item).strip() for item in legacy_scopes if str(item).strip()],
                    "instrument": payload.get("odrl") if isinstance(payload.get("odrl"), dict) else {},
                    "actionStatus": "active",
                }
            ]
        return []

    def _assert_controller_access(self, tenant_id: str, authorization_header: str) -> dict[str, Any]:
        raw_header = str(authorization_header or "").strip()
        if not raw_header.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Bearer token required")
        token = raw_header[7:].strip()
        if not token:
            raise HTTPException(status_code=401, detail="Bearer token required")
        try:
            claims = validate_session_access_token(token, self._deps.settings)
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"invalid Bearer token: {exc}") from exc

        organization = str(claims.get("organization") or "").strip().lower()
        if organization != str(tenant_id or "").strip().lower():
            raise HTTPException(status_code=403, detail="token organization does not match tenant")

        claim_scopes = self._extract_claim_scopes(claims)
        if not _contains_scope("dataconv.tenant.keys.manage", claim_scopes):
            raise HTTPException(status_code=403, detail="insufficient scope: missing dataconv.tenant.keys.manage")
        return claims

    def create_api_key(
        self,
        *,
        tenant_id: str,
        authorization_header: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        claims = self._assert_controller_access(tenant_id, authorization_header)

        actions = self._extract_actions(payload)
        if not actions:
            raise HTTPException(status_code=400, detail="data must contain at least one Action object")

        now = _utcnow()
        expires_in_seconds = payload.get("expires_in_seconds")
        expires_at = ""
        if expires_in_seconds is not None:
            try:
                ttl = int(expires_in_seconds)
            except Exception as exc:
                raise HTTPException(status_code=400, detail="expires_in_seconds must be integer") from exc
            if ttl <= 0:
                raise HTTPException(status_code=400, detail="expires_in_seconds must be > 0")
            expires_at = _iso_utc(now + timedelta(seconds=ttl))

        tenant_token = str(tenant_id or "").strip().lower()
        created_by = str(claims.get("sub") or "").strip()

        current_content, current_entries = self._get_registry(tenant_token)
        response_data: list[dict[str, Any]] = []

        for action in actions:
            agent = action.get("agent") if isinstance(action.get("agent"), dict) else {}
            email = normalize_email(str(agent.get("email") or ""))
            if not email:
                raise HTTPException(status_code=400, detail="agent.email is required for each Action")
            email_hash = hash_email_same_as(email)

            scopes = self._extract_scopes(action)
            if not scopes:
                raise HTTPException(status_code=400, detail="Action scope/target is required")

            action_status = str(action.get("actionStatus") or "active").strip() or "active"
            key_id = str(uuid4())
            api_key = f"dck_{token_urlsafe(24)}"
            key_hash = hash_api_key(api_key)
            operational_subject = str(action.get("operationalSubject") or payload.get("operational_subject") or "").strip()
            instrument_raw = action.get("instrument")
            instrument = instrument_raw if isinstance(instrument_raw, dict) else {}

            entry = {
                "keyId": key_id,
                "keyHash": key_hash,
                "emailHash": email_hash,
                "tenantId": tenant_token,
                "scopes": scopes,
                "target": str(action.get("target") or "").strip(),
                "operationalSubject": operational_subject,
                "instrument": instrument,
                "consentRef": build_consent_ref(
                    tenant_id=tenant_token,
                    email_hash=email_hash,
                    target=str(action.get("target") or "").strip(),
                    scopes=scopes,
                    instrument=instrument,
                ),
                "consentModel": "one-rule-one-consent-one-odrl",
                "actionStatus": action_status,
                "disabled": str(action_status).strip().lower() != "active",
                "createdAt": _iso_utc(now),
                "createdBy": created_by,
                "expiresAt": expires_at,
            }
            current_entries.append(entry)

            response_data.append(
                {
                    "resource": {
                        "@context": "https://schema.org",
                        "@type": "Person",
                        "identifier": key_id,
                        "actionStatus": action_status,
                        "agent": {
                            "sameAs": email_hash,
                        },
                        "target": entry.get("target", ""),
                        "scope": scopes,
                        "instrument": instrument,
                        "consentRef": str(entry.get("consentRef") or "").strip(),
                        "consentModel": str(entry.get("consentModel") or "").strip(),
                        "apiKey": api_key,
                        "tenantId": tenant_token,
                        "expiresAt": expires_at,
                    },
                }
            )

        current_content["keys"] = current_entries
        current_content["registryType"] = "tenant-api-keys"

        self._deps.control_plane.upsert_config(
            self._registry_key(tenant_token),
            current_content,
            updated_by=created_by,
        )

        return {
            "data": response_data,
        }

    def _mutate_api_keys(
        self,
        *,
        tenant_id: str,
        authorization_header: str,
        payload: dict[str, Any],
        remove: bool,
    ) -> dict[str, Any]:
        claims = self._assert_controller_access(tenant_id, authorization_header)
        actions = self._extract_actions(payload)
        if not actions:
            raise HTTPException(status_code=400, detail="data must contain at least one Action object")

        tenant_token = self._normalize_tenant(tenant_id)
        updated_by = str(claims.get("sub") or "").strip()
        current_content, current_entries = self._get_registry(tenant_token)

        response_data: list[dict[str, Any]] = []
        changed = False

        for action in actions:
            key_id = self._extract_action_identifier(action)
            email = self._extract_agent_email(action)
            email_hash = hash_email_same_as(email) if email else ""
            if not key_id and not email_hash:
                raise HTTPException(status_code=400, detail="Action identifier or agent.email is required")

            matched_indexes = [
                index
                for index, item in enumerate(current_entries)
                if str(item.get("tenantId") or "").strip().lower() == tenant_token
                and (
                    (key_id and str(item.get("keyId") or "").strip() == key_id)
                    or (email_hash and str(item.get("emailHash") or "").strip() == email_hash)
                )
            ]
            if not matched_indexes:
                detail = f"api key not found: {key_id}" if key_id else "api key not found for agent.email"
                raise HTTPException(status_code=404, detail=detail)

            matched_items = [dict(current_entries[index]) for index in matched_indexes]
            if remove:
                current_entries = [
                    item for index, item in enumerate(current_entries) if index not in set(matched_indexes)
                ]
                response_data.extend(
                    [self._response_entry_from_registry_item(item, removed=True) for item in matched_items]
                )
            else:
                now = _utcnow()
                for index in matched_indexes:
                    entry = dict(current_entries[index])
                    entry["actionStatus"] = "disabled"
                    entry["disabled"] = True
                    entry["disabledAt"] = _iso_utc(now)
                    entry["disabledBy"] = updated_by
                    current_entries[index] = entry
                    response_data.append(self._response_entry_from_registry_item(entry))
            changed = True

        if not changed:
            return {"data": []}

        current_content["keys"] = current_entries
        current_content["registryType"] = "tenant-api-keys"
        self._deps.control_plane.upsert_config(
            self._registry_key(tenant_token),
            current_content,
            updated_by=updated_by,
        )
        return {
            "data": response_data,
        }

    def disable_api_key(
        self,
        *,
        tenant_id: str,
        authorization_header: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._mutate_api_keys(
            tenant_id=tenant_id,
            authorization_header=authorization_header,
            payload=payload,
            remove=False,
        )

    def remove_api_key(
        self,
        *,
        tenant_id: str,
        authorization_header: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._mutate_api_keys(
            tenant_id=tenant_id,
            authorization_header=authorization_header,
            payload=payload,
            remove=True,
        )

    def list_api_keys(
        self,
        *,
        tenant_id: str,
        authorization_header: str,
    ) -> dict[str, Any]:
        self._assert_controller_access(tenant_id, authorization_header)
        tenant_token = self._normalize_tenant(tenant_id)
        _, entries = self._get_registry(tenant_token)
        data: list[dict[str, Any]] = []
        for item in entries:
            if str(item.get("tenantId") or "").strip().lower() != tenant_token:
                continue
            data.append(self._response_entry_from_registry_item(item))
        return {"data": data}

    def resolve_policy(self, *, tenant_id: str, api_key: str, email: str) -> TenantApiKeyPolicy | None:
        tenant_token = self._normalize_tenant(tenant_id)
        if not tenant_token:
            return None
        key_hash = hash_api_key(api_key)
        email_hash = hash_email_same_as(email)
        if not key_hash or not email_hash:
            return None

        _, entries = self._get_registry(tenant_token)
        now = _utcnow()
        for item in entries:
            if str(item.get("tenantId") or "").strip().lower() != tenant_token:
                continue
            if str(item.get("keyHash") or "").strip().lower() != key_hash:
                continue
            if bool(item.get("disabled", False)):
                continue
            if str(item.get("actionStatus") or "active").strip().lower() != "active":
                continue
            stored_email_hash = str(item.get("emailHash") or "").strip()
            if not stored_email_hash:
                legacy_email = normalize_email(str(item.get("email") or ""))
                stored_email_hash = hash_email_same_as(legacy_email)
            if stored_email_hash != email_hash:
                continue

            expires_at = _parse_iso_utc(str(item.get("expiresAt") or ""))
            if expires_at is not None and expires_at < now:
                continue

            scopes = [
                str(scope or "").strip()
                for scope in (item.get("scopes") if isinstance(item.get("scopes"), list) else [])
                if str(scope or "").strip()
            ]
            if not scopes:
                continue

            operational_subject = str(item.get("operationalSubject") or "").strip()
            odrl_payload = item.get("instrument")
            odrl = odrl_payload if isinstance(odrl_payload, dict) else {}
            return TenantApiKeyPolicy(
                key_id=str(item.get("keyId") or "").strip(),
                tenant_id=tenant_token,
                email_hash=email_hash,
                scopes=scopes,
                operational_subject=operational_subject,
                odrl=odrl,
            )
        return None

    def resolve_policy_without_email(self, *, tenant_id: str, api_key: str) -> TenantApiKeyPolicy | None:
        tenant_token = self._normalize_tenant(tenant_id)
        if not tenant_token:
            return None
        key_hash = hash_api_key(api_key)
        if not key_hash:
            return None

        _, entries = self._get_registry(tenant_token)
        now = _utcnow()
        for item in entries:
            if str(item.get("tenantId") or "").strip().lower() != tenant_token:
                continue
            if str(item.get("keyHash") or "").strip().lower() != key_hash:
                continue
            if bool(item.get("disabled", False)):
                continue
            if str(item.get("actionStatus") or "active").strip().lower() != "active":
                continue

            expires_at = _parse_iso_utc(str(item.get("expiresAt") or ""))
            if expires_at is not None and expires_at < now:
                continue

            scopes = [
                str(scope or "").strip()
                for scope in (item.get("scopes") if isinstance(item.get("scopes"), list) else [])
                if str(scope or "").strip()
            ]
            if not scopes:
                continue

            operational_subject = str(item.get("operationalSubject") or "").strip()
            odrl_payload = item.get("instrument")
            odrl = odrl_payload if isinstance(odrl_payload, dict) else {}
            return TenantApiKeyPolicy(
                key_id=str(item.get("keyId") or "").strip(),
                tenant_id=tenant_token,
                email_hash="",
                scopes=scopes,
                operational_subject=operational_subject,
                odrl=odrl,
            )
        return None
