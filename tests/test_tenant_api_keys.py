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

from adapter_ingestion.service.auth_exchange import issue_session_access_token


def _jwt_none(payload: dict[str, object], header: dict[str, object] | None = None) -> str:
    hdr = header or {"alg": "none", "typ": "JWT"}
    h_raw = json.dumps(hdr, separators=(",", ":"), sort_keys=True).encode("utf-8")
    p_raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    h_b64 = base64.urlsafe_b64encode(h_raw).decode("ascii").rstrip("=")
    p_b64 = base64.urlsafe_b64encode(p_raw).decode("ascii").rstrip("=")
    return f"{h_b64}.{p_b64}.sig"


@unittest.skipIf(TestClient is None, "fastapi runtime dependencies are not installed")
class TenantApiKeyTests(unittest.TestCase):
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
            "DEMO_MODE": "false",
        }
        self._env_patcher = patch.dict(os.environ, env, clear=False)
        self._env_patcher.start()
        sys.modules.pop("adapter_ingestion.service.api", None)
        service_api = importlib.import_module("adapter_ingestion.service.api")
        service_api = importlib.reload(service_api)
        self.app = service_api.create_app()
        self.client = TestClient(self.app)
        self.tenant_id = "VATES-A00000001"

    def tearDown(self) -> None:
        self._env_patcher.stop()

    def _controller_bearer(self) -> str:
        settings = self.app.state.settings
        token, _, _ = issue_session_access_token(
            subject="did:web:globaldatacare.es:employee:controller",
            organization=self.tenant_id,
            scopes=["dataconv.tenant.keys.manage"],
            settings=settings,
        )
        return token

    def _id_token_for_email(self, email: str) -> str:
        now = int(datetime.now(tz=timezone.utc).timestamp())
        return _jwt_none(
            {
                "iss": "https://idp.example.local",
                "sub": "oidc-alice",
                "aud": "dataconv-cli",
                "email": email,
                "iat": now,
                "exp": now + 300,
            }
        )

    def test_create_tenant_api_key_requires_bearer(self) -> None:
        response = self.client.post(
            "/publisher/cds-ES/v1/animal-care/api-key/org.schema/action/_create",
            json={
                "data": [
                    {
                        "resource": {
                            "@context": "https://schema.org",
                            "@type": "UpdateAction",
                            "agent": {"email": "alice@example.com"},
                            "scope": ["dataconv.upload"],
                        },
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 401)

    def test_create_and_exchange_with_tenant_api_key(self) -> None:
        create_response = self.client.post(
            "/publisher/cds-ES/v1/animal-care/api-key/org.schema/action/_create",
            headers={"Authorization": f"Bearer {self._controller_bearer()}"},
            json={
                "data": [
                    {
                        "resource": {
                            "@context": "https://schema.org",
                            "@type": "UpdateAction",
                            "agent": {"email": "alice@example.com"},
                            "target": f"{self.tenant_id.lower()}/cds-*/v1/*/digitaltwin/*/*/_update",
                            "scope": [
                                "dataconv.upload",
                                f"{self.tenant_id.lower()}/cds-*/v1/*/digitaltwin/*/*/_update",
                            ],
                            "instrument": {"permission": [{"action": "update"}]},
                            "actionStatus": "active",
                        },
                    }
                ],
            },
        )
        self.assertEqual(create_response.status_code, 200)
        response_data = create_response.json().get("data")
        self.assertTrue(isinstance(response_data, list) and len(response_data) > 0)
        first_entry = response_data[0] if isinstance(response_data[0], dict) else {}
        resource = first_entry.get("resource") if isinstance(first_entry.get("resource"), dict) else {}
        api_key = str(resource.get("apiKey") or first_entry.get("apiKey") or "")
        self.assertTrue(api_key)

        exchange_response = self.client.post(
            "/exchange",
            json={
                "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
                "subject_token": self._id_token_for_email("alice@example.com"),
                "api_key": api_key,
                "organization": self.tenant_id,
                "scope": f"{self.tenant_id.lower()}/cds-es/v1/animal-care/digitaltwin/sw-x/patient/_update",
            },
        )
        self.assertEqual(exchange_response.status_code, 200, msg=exchange_response.text)
        body = exchange_response.json()
        self.assertEqual(body.get("organization"), self.tenant_id.lower())
        self.assertIn("_update", str(body.get("scope") or ""))
