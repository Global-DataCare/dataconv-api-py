# Flow contract: portal activation validates OIDC plus the controller VP with Connect ICA before persisting a scoped DataConv tenant record.

from __future__ import annotations

from types import SimpleNamespace

import pytest

from adapter_ingestion.runtime import ConfigKey, PreconversionControlPlane
from adapter_ingestion.runtime.adapters import InMemoryConfigStore, InMemoryJobQueue, InMemoryJobStore
from adapter_ingestion.service.managers.organization_tenant_activation import OrganizationTenantActivationManager


class _Verifier:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def verify(self, **request: str) -> dict[str, object]:
        self.calls.append(request)
        return {
            "active": True,
            "controller": "did:web:controller.example#actor-signing",
            "credentialIds": ["org-vc", "rep-vc", "controller-vc"],
            "ledgerChecked": False,
        }


def test_activation_keeps_public_tenant_id_separate_from_storage_scope() -> None:
    control_plane = PreconversionControlPlane(InMemoryConfigStore(), InMemoryJobStore(), InMemoryJobQueue())
    verifier = _Verifier()
    manager = OrganizationTenantActivationManager(
        settings=SimpleNamespace(
            network_mode="test-network",
            default_audience_did="https://dataconv.example",
        ),
        control_plane=control_plane,
        verifier=verifier,
        identity_validator=lambda _: SimpleNamespace(subject="oidc-user"),
    )

    result = manager.activate(
        tenant_id="7654321",
        jurisdiction="CA-BC",
        sector="animal-research",
        id_token="signed-id-token",
        vp_token="signed-controller-vp",
    )

    assert result["tenantId"] == "7654321"
    assert result["networkKind"] == "test-network"
    assert verifier.calls == [{
        "tenant_id": "7654321",
        "jurisdiction": "CA-BC",
        "sector": "animal-research",
        "network_kind": "test-network",
        "audience": "https://dataconv.example",
        "vp_token": "signed-controller-vp",
    }]
    stored = control_plane.resolve_config(ConfigKey(
        alternate_name="7654321",
        manufacturer="dataconv-tenant",
        sector="animal-research",
        manufacturer_version="v1",
        country="CA-BC",
    ))
    assert stored is not None
    assert stored.content["networkKind"] == "test-network"
    assert stored.content["controller"] == "did:web:controller.example#actor-signing"


def test_activation_does_not_persist_when_ica_rejects_the_controller_proof() -> None:
    class _RejectedVerifier:
        def verify(self, **_: str) -> dict[str, object]:
            raise ValueError("ICA credential is revoked")

    control_plane = PreconversionControlPlane(InMemoryConfigStore(), InMemoryJobStore(), InMemoryJobQueue())
    manager = OrganizationTenantActivationManager(
        settings=SimpleNamespace(network_mode="test-network", default_audience_did="https://dataconv.example"),
        control_plane=control_plane,
        verifier=_RejectedVerifier(),
        identity_validator=lambda _: SimpleNamespace(subject="oidc-user"),
    )

    with pytest.raises(ValueError, match="revoked"):
        manager.activate(
            tenant_id="7654321",
            jurisdiction="CA-BC",
            sector="animal-research",
            id_token="signed-id-token",
            vp_token="signed-controller-vp",
        )
    assert control_plane.resolve_config(ConfigKey(
        alternate_name="7654321",
        manufacturer="dataconv-tenant",
        sector="animal-research",
        manufacturer_version="v1",
        country="CA-BC",
    )) is None
