from __future__ import annotations

import base64
import importlib
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover - optional runtime dependency
    TestClient = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapter_ingestion.service.auth_exchange import hash_email_same_as


def _jwt_none(payload: dict[str, object], header: dict[str, object] | None = None) -> str:
    hdr = header or {"alg": "none", "typ": "JWT"}
    h_raw = json.dumps(hdr, separators=(",", ":"), sort_keys=True).encode("utf-8")
    p_raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    h_b64 = base64.urlsafe_b64encode(h_raw).decode("ascii").rstrip("=")
    p_b64 = base64.urlsafe_b64encode(p_raw).decode("ascii").rstrip("=")
    return f"{h_b64}.{p_b64}.sig"


@unittest.skipIf(TestClient is None, "fastapi runtime dependencies are not installed")
class ExchangeFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        env = {
            "NODE_ENV": "test",
            "HOST_INTERNAL_IP": "127.0.0.1",
            "PORT": "8080",
            "DB_PROVIDER": "mem",
            "QUEUE_PROVIDER": "mem",
            "STORAGE_PROVIDER": "mem",
            "PRECONV_LOCAL_DATA_DIR": str(ROOT / "artifacts" / "test-runtime"),
            "PRECONV_DEFAULT_SPECIES_FHIR_FILE": str(
                ROOT / "configs" / "fhir-target-species.template.editable.json"
            ),
            "EXCHANGE_ALLOW_INSECURE_ASSERTIONS": "true",
            "EXCHANGE_SESSION_TOKEN_SECRET": "test-session-secret",
            "EXCHANGE_DEFAULT_ALLOWED_SCOPES": "dataconv.upload dataconv.read",
            "LOCAL_EXCHANGE_ALLOW_API_KEY": "true",
            "LOCAL_EXCHANGE_ALLOW_API_KEY_EXCEPTION": "true",
            "LOCAL_EXCHANGE_API_KEYS": "demo-key",
            "LOCAL_EXCHANGE_API_KEY_SUBJECT_DEFAULT": "did:web:globaldatacare.es:employee:controller",
            "LOCAL_EXCHANGE_API_KEY_ORG_DEFAULT": "VATES-A00000001",
            "DEMO_MODE": "false",
        }
        self._env_patcher = patch.dict(os.environ, env, clear=False)
        self._env_patcher.start()
        sys.modules.pop("adapter_ingestion.service.api", None)
        service_api = importlib.import_module("adapter_ingestion.service.api")
        service_api = importlib.reload(service_api)
        self.app = service_api.create_app()
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self._env_patcher.stop()

    def _build_exchange_payload(self, *, same_as_hash: str, scope: str = "dataconv.upload") -> dict[str, object]:
        now = int(datetime.now(tz=timezone.utc).timestamp())
        email = "alice@example.com"
        id_token = _jwt_none(
            {
                "iss": "https://idp.example.local",
                "sub": "oidc-alice",
                "aud": "dataconv-cli",
                "email": email,
                "iat": now,
                "exp": now + 300,
            }
        )
        vp_token = _jwt_none(
            {
                "iss": "did:web:wallet.example:holder:alice",
                "sub": "did:web:wallet.example:holder:alice",
                "jti": "vp-001",
                "vp": {
                    "holder": "did:web:wallet.example:holder:alice",
                    "verifiableCredential": [
                        {
                            "credentialSubject": {
                                "id": "did:web:globaldatacare.es:employee:controller",
                                "sameAs": same_as_hash,
                                "organization": "VATES-A00000001",
                                "scopes": ["dataconv.upload", "dataconv.read"],
                            }
                        }
                    ]
                },
            },
            header={"alg": "none", "typ": "JWT", "kid": "wallet-key-1"},
        )
        client_assertion = _jwt_none(
            {
                "iss": "did:web:wallet.example:holder:alice",
                "sub": "did:web:wallet.example:holder:alice",
                "aud": "http://testserver/exchange",
                "iat": now,
                "exp": now + 300,
                "jti": "assertion-001",
                "vp_jti": "vp-001",
            },
            header={"alg": "none", "typ": "JWT", "kid": "wallet-key-1"},
        )
        return {
            "subject_token": id_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
            "vp_token": vp_token,
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": client_assertion,
            "scope": scope,
        }

    def test_hash_email_same_as_matches_expected(self) -> None:
        self.assertEqual(
            hash_email_same_as("Alice@Example.Com "),
            hash_email_same_as("alice@example.com"),
        )

    def test_exchange_valid(self) -> None:
        payload = self._build_exchange_payload(same_as_hash=hash_email_same_as("alice@example.com"))
        response = self.client.post("/exchange", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access_token", data)
        self.assertEqual(data.get("token_type"), "Bearer")
        self.assertIn("dataconv.upload", str(data.get("scope") or ""))

    def test_exchange_invalid_email_hash_mismatch(self) -> None:
        payload = self._build_exchange_payload(same_as_hash="deadbeef")
        response = self.client.post("/exchange", json=payload)
        self.assertEqual(response.status_code, 401)
        self.assertIn("sameAs", str(response.text))

    def test_upload_authorized_with_exchange_token(self) -> None:
        payload = self._build_exchange_payload(same_as_hash=hash_email_same_as("alice@example.com"), scope="dataconv.upload")
        exchange_response = self.client.post("/exchange", json=payload)
        self.assertEqual(exchange_response.status_code, 200)
        access_token = exchange_response.json().get("access_token")
        self.assertTrue(isinstance(access_token, str) and access_token)

        upload_payload = {
            "iss": "did:web:test.example:employee:loader",
            "type": "https://didcomm.org/plaintext/2.0/message",
            "thid": "job-exchange-001",
            "jti": "job-exchange-001",
            "iat": 1760000000,
            "exp": 1760003600,
            "inputRef": "mem://uploads/input.xlsx",
        }
        upload_response = self.client.post(
            "/tenant-a/cds-es/v1/onehealth-research/digitaltwin/qvet/Composition/_upload",
            json=upload_payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        self.assertEqual(upload_response.status_code, 202)

    def test_upload_denied_with_insufficient_scope(self) -> None:
        payload = self._build_exchange_payload(same_as_hash=hash_email_same_as("alice@example.com"), scope="dataconv.read")
        exchange_response = self.client.post("/exchange", json=payload)
        self.assertEqual(exchange_response.status_code, 200)
        access_token = exchange_response.json().get("access_token")

        upload_payload = {
            "iss": "did:web:test.example:employee:loader",
            "type": "https://didcomm.org/plaintext/2.0/message",
            "thid": "job-exchange-002",
            "jti": "job-exchange-002",
            "iat": 1760000000,
            "exp": 1760003600,
            "inputRef": "mem://uploads/input.xlsx",
        }
        upload_response = self.client.post(
            "/tenant-a/cds-es/v1/onehealth-research/digitaltwin/qvet/Composition/_upload",
            json=upload_payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        self.assertEqual(upload_response.status_code, 403)
        self.assertIn("insufficient scope", str(upload_response.text).lower())

    def test_exchange_allows_api_key_mode_without_vp_and_assertion(self) -> None:
        now = int(datetime.now(tz=timezone.utc).timestamp())
        id_token = _jwt_none(
            {
                "iss": "https://idp.example.local",
                "sub": "oidc-alice",
                "aud": "dataconv-cli",
                "email": "alice@example.com",
                "iat": now,
                "exp": now + 300,
            }
        )
        response = self.client.post(
            "/exchange",
            json={
                "subject_token": id_token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
                "scope": "dataconv.upload",
            },
            headers={"X-API-Key": "demo-key"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access_token", data)
        self.assertEqual(data.get("organization"), "VATES-A00000001")

    def test_exchange_rejects_api_key_without_id_token(self) -> None:
        response = self.client.post(
            "/exchange",
            json={
                "subject_token": "",
                "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
                "scope": "dataconv.upload",
            },
            headers={"X-API-Key": "demo-key"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("subject_token", str(response.text))

    def test_exchange_allows_explicit_api_key_exception_profile_without_id_token(self) -> None:
        response = self.client.post(
            "/exchange",
            json={
                "api_key_profile": "api-key-exception.v1",
                "scope": "dataconv.upload",
                "organization": "VATES-A00000001",
            },
            headers={"X-API-Key": "demo-key"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("access_token", payload)
        self.assertEqual(payload.get("organization"), "VATES-A00000001")
