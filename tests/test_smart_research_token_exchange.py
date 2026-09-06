# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.
# A DCR-bound professional exchanges one GW-signed study SMART token for a
# short-lived DataConv token that cannot escape its tenant or ResearchStudy.

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from adapter_ingestion.service.api_support import HTTPException, _enforce_auth_context
from adapter_ingestion.service.auth_exchange import (
    issue_session_access_token,
    parse_jwt_unverified,
    validate_session_access_token,
)
from adapter_ingestion.service.managers.smart_research_token_exchange import (
    SMART_ACCESS_TOKEN_TYPE,
    SmartResearchTokenExchangeManager,
    did_web_document_url,
)
from adapter_ingestion.service.routes_exchange import register_exchange_routes


ISSUER = "did:web:gw.example:tenant:research"
ACTOR = "did:web:professional.example:employee:reviewer"
TENANT = "CA-BC-7654321"
STUDY = "ResearchStudy/study-2026-01"
SMART_SCOPE = f"organization/ResearchSubject.crus?study={STUDY}"
KEY_ID = "comm_sig"
VERIFICATION_METHOD_ID = f"{ISSUER}#{KEY_ID}"


def _public_jwk(private_key: ec.EllipticCurvePrivateKey) -> dict[str, str]:
    public_jwk = jwt.algorithms.ECAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    return {**public_jwk, "kid": KEY_ID, "alg": "ES384", "use": "sig"}


def _smart_token(private_key: ec.EllipticCurvePrivateKey, **overrides: object) -> str:
    now = int(datetime.now(tz=timezone.utc).timestamp())
    claims: dict[str, object] = {
        "iss": ISSUER,
        "sub": ACTOR,
        "aud": ISSUER,
        "scope": SMART_SCOPE,
        "purpose": "HRESCH",
        "study": STUDY,
        "iat": now,
        "nbf": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="ES384", headers={"kid": KEY_ID})


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        demo_mode=False,
        network_mode="test-network",
        smart_gw_allowed_issuers=(ISSUER,),
        smart_gw_expected_audiences=(ISSUER,),
        smart_gw_issuer_tenant_bindings={ISSUER: TENANT},
        smart_gw_did_cache_ttl_seconds=300,
        smart_gw_http_timeout_seconds=2,
        exchange_session_token_secret="test-session-secret",
        exchange_session_token_ttl_seconds=900,
        default_issuer_did="did:web:dataconv.example",
        default_audience_did="did:web:dataconv.example",
    )


def _manager(private_key: ec.EllipticCurvePrivateKey) -> SmartResearchTokenExchangeManager:
    did_document = {
        "id": ISSUER,
        "verificationMethod": [{
            "id": VERIFICATION_METHOD_ID,
            "controller": ISSUER,
            "type": "JsonWebKey2020",
            "publicKeyJwk": _public_jwk(private_key),
        }],
        "authentication": [VERIFICATION_METHOD_ID],
    }
    return SmartResearchTokenExchangeManager(
        _settings(),
        did_document_loader=lambda url, timeout: did_document,
    )


def test_resolves_standard_did_web_paths_and_restricts_local_http_to_test_modes() -> None:
    assert did_web_document_url(ISSUER, demo_mode=False) == "https://gw.example/tenant/research/did.json"
    assert did_web_document_url("did:web:localhost%3A3200:tenant", demo_mode=True) == (
        "http://localhost:3200/tenant/did.json"
    )
    with pytest.raises(ValueError, match="HTTPS"):
        did_web_document_url("did:web:localhost%3A3200:tenant", demo_mode=False)


def test_exchanges_verified_smart_access_token_for_minimal_study_bound_dataconv_scopes() -> None:
    private_key = ec.generate_private_key(ec.SECP384R1())
    manager = _manager(private_key)

    result = manager.exchange(
        {
            "subject_token": _smart_token(private_key),
            "subject_token_type": SMART_ACCESS_TOKEN_TYPE,
        },
        tenant_id=TENANT,
        jurisdiction="CA-BC",
        sector="animal-research",
    )

    claims = validate_session_access_token(result.access_token, _settings())
    assert result.subject == ACTOR
    assert result.organization == TENANT
    assert result.study == STUDY
    assert 1 <= result.expires_in <= 300
    assert result.granted_scopes == ["dataconv.upload", "dataconv.read", "dataconv.review"]
    assert claims["actor"] == ACTOR
    assert claims["organization"] == TENANT
    assert claims["study"] == STUDY
    assert claims["purpose"] == "HRESCH"
    assert claims["token_profile"] == "professional_research"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"aud": "did:web:other.example"}, "[Aa]udience"),
        ({"purpose": "TREAT"}, "purpose"),
        ({"study": "ResearchStudy/other"}, "scope"),
        ({"study": "https://gw.example/fhir/ResearchStudy/study-2026-01"}, "relative"),
        ({"scope": "organization/ResearchSubject.rus?study=ResearchStudy/study-2026-01"}, "scope"),
        ({"sub": ISSUER}, "professional"),
        ({"exp": 1}, "expired"),
    ],
)
def test_rejects_smart_claims_that_do_not_prove_exact_professional_study_access(
    override: dict[str, object],
    message: str,
) -> None:
    private_key = ec.generate_private_key(ec.SECP384R1())
    with pytest.raises(ValueError, match=message):
        _manager(private_key).exchange(
            {
                "subject_token": _smart_token(private_key, **override),
                "subject_token_type": SMART_ACCESS_TOKEN_TYPE,
            },
            tenant_id=TENANT,
            jurisdiction="CA-BC",
            sector="animal-research",
        )


def test_rejects_wrong_subject_token_type_signature_key_algorithm_and_tenant_binding() -> None:
    private_key = ec.generate_private_key(ec.SECP384R1())
    manager = _manager(private_key)
    request = {"subject_token": _smart_token(private_key), "subject_token_type": SMART_ACCESS_TOKEN_TYPE}

    with pytest.raises(ValueError, match="subject_token_type"):
        manager.exchange({**request, "subject_token_type": "urn:ietf:params:oauth:token-type:id_token"}, tenant_id=TENANT, jurisdiction="CA-BC", sector="animal-research")
    with pytest.raises(ValueError, match="unexpected"):
        manager.exchange({**request, "vp_token": "controller-proof"}, tenant_id=TENANT, jurisdiction="CA-BC", sector="animal-research")
    with pytest.raises(ValueError, match="tenant"):
        manager.exchange(request, tenant_id="another-tenant", jurisdiction="CA-BC", sector="animal-research")

    other_key = ec.generate_private_key(ec.SECP384R1())
    with pytest.raises(ValueError, match="signature"):
        manager.exchange(
            {"subject_token": _smart_token(other_key), "subject_token_type": SMART_ACCESS_TOKEN_TYPE},
            tenant_id=TENANT,
            jurisdiction="CA-BC",
            sector="animal-research",
        )

    header, payload = parse_jwt_unverified(_smart_token(private_key))
    forged_alg = jwt.encode(
        payload,
        ec.generate_private_key(ec.SECP256R1()),
        algorithm="ES256",
        headers={"kid": header["kid"]},
    )
    with pytest.raises(ValueError, match="algorithm"):
        manager.exchange(
            {"subject_token": forged_alg, "subject_token_type": SMART_ACCESS_TOKEN_TYPE},
            tenant_id=TENANT,
            jurisdiction="CA-BC",
            sector="animal-research",
        )


def test_research_operations_reject_controller_tokens_and_cross_study_professional_tokens() -> None:
    settings = _settings()
    demo_settings = SimpleNamespace(**{**vars(settings), "demo_mode": True, "network_mode": "test"})
    with pytest.raises(HTTPException, match="Bearer token required"):
        _enforce_auth_context(
            {"iss": ACTOR},
            demo_settings,
            expected_organization=TENANT,
            expected_research_study=STUDY,
            require_professional_research=True,
        )
    controller_token, _, _ = issue_session_access_token(
        subject="did:web:controller.example",
        organization=TENANT,
        scopes=["dataconv.upload"],
        settings=settings,
    )
    with pytest.raises(HTTPException, match="professional"):
        _enforce_auth_context(
            {},
            settings,
            authorization_header=f"Bearer {controller_token}",
            required_scopes={"dataconv.upload"},
            expected_organization=TENANT,
            expected_research_study=STUDY,
            require_professional_research=True,
        )

    professional_token, _, _ = issue_session_access_token(
        subject=ACTOR,
        organization=TENANT,
        scopes=["dataconv.upload", "dataconv.read", "dataconv.review"],
        settings=settings,
        additional_claims={
            "actor": ACTOR,
            "study": "ResearchStudy/other",
            "purpose": "HRESCH",
            "token_profile": "professional_research",
        },
    )
    with pytest.raises(HTTPException, match="ResearchStudy"):
        _enforce_auth_context(
            {},
            settings,
            authorization_header=f"Bearer {professional_token}",
            required_scopes={"dataconv.review"},
            expected_organization=TENANT,
            expected_research_study=STUDY,
            require_professional_research=True,
        )

    correct_study_token, _, _ = issue_session_access_token(
        subject=ACTOR,
        organization=TENANT,
        scopes=["dataconv.upload"],
        settings=settings,
        additional_claims={
            "actor": ACTOR,
            "study": STUDY,
            "purpose": "HRESCH",
            "token_profile": "professional_research",
        },
    )
    with pytest.raises(HTTPException, match="actor"):
        _enforce_auth_context(
            {"iss": "did:web:another-professional.example"},
            settings,
            authorization_header=f"Bearer {correct_study_token}",
            required_scopes={"dataconv.upload"},
            expected_organization=TENANT,
            expected_research_study=STUDY,
            require_professional_research=True,
        )


def test_professional_exchange_route_accepts_only_the_rfc8693_wire_fields() -> None:
    fastapi = pytest.importorskip("fastapi")
    testclient = pytest.importorskip("fastapi.testclient")
    captured: dict[str, object] = {}

    class SmartManager:
        def exchange(self, payload: dict[str, object], **context: str) -> SimpleNamespace:
            captured.update({"payload": payload, **context})
            return SimpleNamespace(
                access_token="issued-token",
                token_type="Bearer",
                expires_in=300,
                scope="dataconv.upload dataconv.read dataconv.review",
                granted_scopes=["dataconv.upload", "dataconv.read", "dataconv.review"],
                subject=ACTOR,
                organization=TENANT,
                study=STUDY,
            )

        @staticmethod
        def as_response(result: SimpleNamespace) -> dict[str, object]:
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

    app = fastapi.FastAPI()
    register_exchange_routes(
        app,
        exchange_manager=SimpleNamespace(),
        smart_research_exchange_manager=SmartManager(),
    )
    response = testclient.TestClient(app).post(
        f"/publisher/cds-CA-BC/v1/animal-research/{TENANT}/professional/research/auth/_exchange",
        json={"subject_token": "gw-smart-token", "subject_token_type": SMART_ACCESS_TOKEN_TYPE},
    )

    assert response.status_code == 200
    assert captured == {
        "payload": {"subject_token": "gw-smart-token", "subject_token_type": SMART_ACCESS_TOKEN_TYPE},
        "tenant_id": TENANT,
        "jurisdiction": "CA-BC",
        "sector": "animal-research",
    }
    assert response.json()["study"] == STUDY


def test_exchange_requires_an_active_dataconv_tenant_before_did_resolution() -> None:
    private_key = ec.generate_private_key(ec.SECP384R1())
    manager = SmartResearchTokenExchangeManager(
        _settings(),
        did_document_loader=lambda _url, _timeout: pytest.fail("DID resolution must not run"),
        tenant_is_active=lambda _tenant, _jurisdiction, _sector: False,
    )
    with pytest.raises(PermissionError, match="not active"):
        manager.exchange(
            {"subject_token": _smart_token(private_key), "subject_token_type": SMART_ACCESS_TOKEN_TYPE},
            tenant_id=TENANT,
            jurisdiction="CA-BC",
            sector="animal-research",
        )
