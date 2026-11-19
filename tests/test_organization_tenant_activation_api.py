# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.

from __future__ import annotations

import base64
import importlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _jwt_none(payload: dict[str, object]) -> str:
    encode = lambda value: base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
    return f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode(payload)}.sig"


@pytest.mark.parametrize("phone_sign_in", [False, True])
def test_activation_endpoint_uses_path_scope_and_preserves_legal_tenant_identifier(phone_sign_in: bool) -> None:
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
    issuer = "https://securetoken.google.com/dataconv" if phone_sign_in else "https://idp.example"
    env["EXCHANGE_OIDC_ISSUER"] = issuer
    env["EXCHANGE_OIDC_AUDIENCE"] = "dataconv"
    now = int(datetime.now(timezone.utc).timestamp())
    contact_claims = (
        {"phone_number": "+12025550101", "firebase": {"sign_in_provider": "phone"}}
        if phone_sign_in else {"email": "controller@example.com"}
    )
    id_token = _jwt_none({
        "iss": issuer,
        "sub": "oidc-user",
        "aud": "dataconv",
        **contact_claims,
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
            client = TestClient(api.create_app())
            if phone_sign_in:
                forged_contact = _jwt_none({
                    "iss": issuer, "sub": "oidc-user", "aud": "dataconv",
                    "firebase": {"sign_in_provider": "custom"},
                    "phone_number": "+12025550101", "iat": now, "exp": now + 300,
                })
                denied = client.post(
                    "/publisher/cds-CA-BC/v1/animal-research/7654321/organization/tenant/_activate",
                    json={"id_token": forged_contact, "vp_token": "signed-controller-vp"},
                )
                assert denied.status_code == 401
            pending = client.post(
                "/publisher/cds-CA-BC/v1/animal-research/7654321/organization/tenant/_status",
                json={"id_token": id_token, "vp_token": "signed-controller-vp"},
            )
            response = client.post(
                "/publisher/cds-CA-BC/v1/animal-research/7654321/organization/tenant/_activate",
                json={"id_token": id_token, "vp_token": "signed-controller-vp"},
            )
            ready = client.post(
                "/publisher/cds-CA-BC/v1/animal-research/7654321/organization/tenant/_status",
                json={"id_token": id_token, "vp_token": "signed-controller-vp"},
            )

    assert pending.status_code == 200
    assert pending.json() == {
        "active": False,
        "status": "not-configured",
        "tenantId": "7654321",
        "networkKind": "test-network",
        "jurisdiction": "CA-BC",
        "sector": "animal-research",
    }
    assert response.status_code == 200
    assert response.json()["tenantId"] == "7654321"
    assert response.json()["networkKind"] == "test-network"
    assert ready.status_code == 200
    assert ready.json()["active"] is True
    assert ready.json()["status"] == "ready"


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
            client = TestClient(api.create_app())
            inactive = client.post(
                "/publisher/cds-CA-BC/v1/animal-research/7654321/organization/research/auth/_exchange",
                json={"id_token": id_token, "vp_token": "signed-controller-vp"},
            )
            activated = client.post(
                "/publisher/cds-CA-BC/v1/animal-research/7654321/organization/tenant/_activate",
                json={"id_token": id_token, "vp_token": "signed-controller-vp"},
            )
            response = client.post(
                "/publisher/cds-CA-BC/v1/animal-research/7654321/organization/research/auth/_exchange",
                json={"id_token": id_token, "vp_token": "signed-controller-vp"},
            )

    assert inactive.status_code == 403
    assert activated.status_code == 200
    assert response.status_code == 200
    assert response.json()["token_type"] == "Bearer"


def test_signed_firebase_phone_token_requires_an_explicitly_trusted_project() -> None:
    from types import SimpleNamespace
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from adapter_ingestion.service import auth_exchange

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    issuer = "https://securetoken.google.com/dataconv"
    now = int(datetime.now(timezone.utc).timestamp())
    token = jwt.encode({
        "iss": issuer, "sub": "oidc-user", "aud": "dataconv",
        "firebase": {"sign_in_provider": "phone"}, "phone_number": "+12025550101",
        "iat": now, "exp": now + 300,
    }, private_key, algorithm="RS256", headers={"kid": "fixture-firebase-key"})
    with patch.object(auth_exchange, "_load_jwks_cached", return_value={
        "keys": [{**public_jwk, "kid": "fixture-firebase-key"}],
    }):
        settings = SimpleNamespace(exchange_allow_insecure_assertions=False, exchange_oidc_audience="dataconv")
        with pytest.raises(ValueError):
            auth_exchange.validate_id_token(token, settings, allow_firebase_phone=True)
        settings.exchange_oidc_issuer = issuer
        identity = auth_exchange.validate_id_token(token, settings, allow_firebase_phone=True)
        assert identity.subject == "oidc-user"
        assert identity.email == ""
        with pytest.raises(ValueError, match="missing email claim"):
            auth_exchange.validate_id_token(token, settings)
