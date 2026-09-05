# Flow contract: the portal-facing activation route validates ICA proof before returning and persisting an active DataConv tenant.

from __future__ import annotations

import base64
import importlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _jwt_none(payload: dict[str, object]) -> str:
    encode = lambda value: base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
    return f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode(payload)}.sig"


def test_activation_endpoint_uses_path_scope_and_preserves_legal_tenant_identifier() -> None:
    env = {
        "NODE_ENV": "test",
        "DB_PROVIDER": "mem",
        "SEARCH_PROVIDER": "mem",
        "QUEUE_PROVIDER": "mem",
        "STORAGE_PROVIDER": "mem",
        "NETWORK_MODE": "test-network",
        "PRECONV_ICA_BASE_URL": "https://ica.example",
        "PRECONV_ICA_API_KEY": "service-key",
        "PRECONV_DEFAULT_AUDIENCE_DID": "https://dataconv.example",
        "EXCHANGE_ALLOW_INSECURE_ASSERTIONS": "true",
        "DEMO_MODE": "false",
    }
    now = int(datetime.now(timezone.utc).timestamp())
    id_token = _jwt_none({
        "iss": "https://idp.example",
        "sub": "oidc-user",
        "aud": "dataconv",
        "email": "controller@example.com",
        "iat": now,
        "exp": now + 300,
    })
    with patch.dict(os.environ, env, clear=False):
        sys.modules.pop("adapter_ingestion.service.api", None)
        api = importlib.reload(importlib.import_module("adapter_ingestion.service.api"))
        with patch(
            "adapter_ingestion.service.managers.organization_tenant_activation.ConnectIcaOrganizationProofVerifierClient.verify",
            return_value={
                "active": True,
                "controller": "did:web:controller.example#actor-signing",
                "credentialIds": ["org-vc", "rep-vc", "controller-vc"],
                "ledgerChecked": False,
            },
        ):
            response = TestClient(api.create_app()).post(
                "/publisher/cds-CA-BC/v1/animal-research/7654321/organization/tenant/_activate",
                json={"id_token": id_token, "vp_token": "signed-controller-vp"},
            )

    assert response.status_code == 200
    assert response.json()["tenantId"] == "7654321"
    assert response.json()["networkKind"] == "test-network"


def test_controller_upload_exchange_uses_the_same_ica_proof_and_route_scope() -> None:
    env = {
        "NODE_ENV": "test", "DB_PROVIDER": "mem", "SEARCH_PROVIDER": "mem",
        "QUEUE_PROVIDER": "mem", "STORAGE_PROVIDER": "mem", "NETWORK_MODE": "test-network",
        "PRECONV_ICA_BASE_URL": "https://ica.example", "PRECONV_ICA_API_KEY": "service-key",
        "PRECONV_DEFAULT_AUDIENCE_DID": "https://dataconv.example",
        "EXCHANGE_ALLOW_INSECURE_ASSERTIONS": "true", "EXCHANGE_SESSION_TOKEN_SECRET": "test-secret",
        "DEMO_MODE": "false",
    }
    now = int(datetime.now(timezone.utc).timestamp())
    id_token = _jwt_none({
        "iss": "https://idp.example", "sub": "oidc-user", "aud": "dataconv",
        "email": "controller@example.com", "iat": now, "exp": now + 300,
    })
    with patch.dict(os.environ, env, clear=False):
        sys.modules.pop("adapter_ingestion.service.api", None)
        api = importlib.reload(importlib.import_module("adapter_ingestion.service.api"))
        with patch(
            "adapter_ingestion.service.managers.organization_tenant_activation.ConnectIcaOrganizationProofVerifierClient.verify",
            return_value={"active": True, "controller": "did:web:controller.example#actor-signing", "credentialIds": ["org-vc", "rep-vc", "controller-vc"], "ledgerChecked": False},
        ):
            response = TestClient(api.create_app()).post(
                "/publisher/cds-CA-BC/v1/animal-research/7654321/organization/research/auth/_exchange",
                json={"id_token": id_token, "vp_token": "signed-controller-vp"},
            )

    assert response.status_code == 200
    assert response.json()["token_type"] == "Bearer"
