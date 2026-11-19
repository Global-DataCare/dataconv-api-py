# Flow contract: a trusted Demo BFF assertion opens only workbook rights for one active Demo tenant route, actor and study.
from datetime import datetime, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adapter_ingestion.service.auth_exchange import validate_session_access_token
from adapter_ingestion.service.managers.demo_research_workbook_exchange import DemoResearchWorkbookExchangeManager
from adapter_ingestion.service.routes_exchange import register_exchange_routes


ISSUER = "https://professional.example"
AUDIENCE = "https://dataconv.example"
TENANT = "CA-BC-7654321"
JURISDICTION = "CA-BC"
SECTOR = "animal-research"
STUDY = "ResearchStudy/3dac02a4-22fa-458d-bc6e-0c767a9e4f03"
ACTOR = "urn:uuid:36f8f299-65a8-43e6-9e7c-081db9f6140f"


@pytest.fixture
def exchange_fixture():
    key = ec.generate_private_key(ec.SECP256R1())
    settings = SimpleNamespace(
        network_mode="demo", demo_mode=False,
        demo_research_assertion_issuer=ISSUER, demo_research_assertion_audience=AUDIENCE,
        demo_research_assertion_public_jwk=jwt.algorithms.ECAlgorithm.to_jwk(key.public_key()),
        exchange_session_token_secret="test-session-secret", exchange_session_token_ttl_seconds=900,
        default_issuer_did=AUDIENCE, default_audience_did=AUDIENCE,
    )
    now = int(datetime.now(timezone.utc).timestamp())
    claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": ACTOR, "tenant": TENANT, "jurisdiction": JURISDICTION,
              "sector": SECTOR, "study": STUDY, "purpose": "HRESCH", "iat": now, "nbf": now, "exp": now + 60}
    route = {"tenant_id": TENANT, "jurisdiction": JURISDICTION, "sector": SECTOR}
    manager = DemoResearchWorkbookExchangeManager(settings, tenant_is_active=lambda *args: args == (TENANT, JURISDICTION, SECTOR))
    return manager, key, settings, claims, route


def test_exchanges_a_pinned_demo_grant_for_short_lived_workbook_access(exchange_fixture):
    manager, key, settings, claims, route = exchange_fixture
    grant = manager.exchange(jwt.encode(claims, key, algorithm="ES256"), **route)
    result = validate_session_access_token(grant.access_token, settings, force_secure=True)
    assert result["actor"] == result["sub"] == ACTOR
    assert result["organization"] == TENANT
    assert result["study"] == STUDY
    assert "dataconv.review" in grant.granted_scopes
    assert "dataconv.config.write" not in grant.granted_scopes
    assert grant.expires_in <= 60


@pytest.mark.parametrize("altered", [{"aud": ISSUER}, {"tenant": "foreign"}, {"jurisdiction": "US"},
                                     {"sector": "health-care"}, {"study": "ResearchStudy/unbound"}, {"purpose": "TREAT"}])
def test_denies_assertions_for_a_different_scope(exchange_fixture, altered):
    manager, key, _, claims, route = exchange_fixture
    with pytest.raises(ValueError):
        manager.exchange(jwt.encode({**claims, **altered}, key, algorithm="ES256"), **route)


def test_demo_exchange_is_disabled_in_test_network_and_legacy_demo_mode(exchange_fixture):
    manager, key, settings, claims, route = exchange_fixture
    token = jwt.encode(claims, key, algorithm="ES256")
    settings.network_mode = "test"
    with pytest.raises(PermissionError):
        manager.exchange(token, **route)
    settings.network_mode = "demo"
    settings.demo_mode = True
    with pytest.raises(PermissionError):
        manager.exchange(token, **route)


def test_denies_inactive_tenant_long_lifetime_and_forged_signature(exchange_fixture):
    manager, key, settings, claims, route = exchange_fixture
    inactive = DemoResearchWorkbookExchangeManager(settings, tenant_is_active=lambda *_: False)
    with pytest.raises(PermissionError):
        inactive.exchange(jwt.encode(claims, key, algorithm="ES256"), **route)
    with pytest.raises(ValueError):
        manager.exchange(jwt.encode({**claims, "exp": claims["iat"] + 3600}, key, algorithm="ES256"), **route)
    with pytest.raises(ValueError):
        manager.exchange(jwt.encode(claims, ec.generate_private_key(ec.SECP256R1()), algorithm="ES256"), **route)


def test_route_accepts_only_the_assertion_field_and_disables_caching(exchange_fixture):
    manager, key, _, claims, _ = exchange_fixture
    app = FastAPI()
    register_exchange_routes(app, exchange_manager=None, demo_research_workbook_exchange_manager=manager)
    client = TestClient(app)
    path = f"/publisher/cds-{JURISDICTION}/v1/{SECTOR}/{TENANT}/research/auth/_demo-exchange"
    assertion = jwt.encode(claims, key, algorithm="ES256")
    assert client.post(path, json={"assertion": assertion, "organization": TENANT}).status_code == 400
    response = client.post(path, json={"assertion": assertion})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["study"] == STUDY


def test_real_demo_app_checks_activation_and_uses_its_token_for_coding_review(exchange_fixture, monkeypatch, tmp_path):
    _, key, settings, claims, _ = exchange_fixture
    monkeypatch.chdir(tmp_path)
    for name, value in {
        "NODE_ENV": "test", "DEMO_MODE": "false", "NETWORK_MODE": "demo",
        "DB_PROVIDER": "mem", "SEARCH_PROVIDER": "mem", "QUEUE_PROVIDER": "mem", "STORAGE_PROVIDER": "mem",
        "PRECONV_LOCAL_DATA_DIR": str(tmp_path), "SUPPORTED_JURISDICTIONS": JURISDICTION, "SUPPORTED_SECTORS": SECTOR,
        "EXCHANGE_SESSION_TOKEN_SECRET": settings.exchange_session_token_secret,
        "DEMO_RESEARCH_ASSERTION_ISSUER": ISSUER, "DEMO_RESEARCH_ASSERTION_AUDIENCE": AUDIENCE,
        "DEMO_RESEARCH_ASSERTION_PUBLIC_JWK": settings.demo_research_assertion_public_jwk,
    }.items():
        monkeypatch.setenv(name, value)
    from adapter_ingestion.service.api import ConfigKey, create_app

    app = create_app()
    client = TestClient(app)
    route = f"/publisher/cds-{JURISDICTION}/v1/{SECTOR}/{TENANT}"
    assertion = jwt.encode(claims, key, algorithm="ES256")
    endpoint = f"{route}/research/auth/_demo-exchange"
    assert client.post(endpoint, json={"assertion": assertion}).status_code == 403
    app.state.control_plane.upsert_config(
        ConfigKey(alternate_name=TENANT, manufacturer="dataconv-tenant", sector=SECTOR, manufacturer_version="v1", country=JURISDICTION),
        {"active": True, "networkKind": "demo"},
    )
    exchange = client.post(endpoint, json={"assertion": assertion})
    assert exchange.status_code == 200
    headers = {"Authorization": "Bearer " + exchange.json()["access_token"]}
    request = {"resourceType": "Parameters", "parameter": [{"name": "study", "valueReference": {"reference": STUDY}}]}
    review = client.post(f"{route}/dataset/ResearchSubject/$review-pending", headers=headers, json=request)
    assert review.status_code == 200
    assert review.json()["total"] == 0
    request["parameter"][0]["valueReference"]["reference"] = "ResearchStudy/other-study"
    assert client.post(f"{route}/dataset/ResearchSubject/$review-pending", headers=headers, json=request).status_code == 403

    monkeypatch.setenv("NETWORK_MODE", "test")
    assert TestClient(create_app()).post(endpoint, json={"assertion": assertion}).status_code == 404
