# Flow contract: public tenant identity remains unchanged while every stored and indexed twin is isolated by deployment scope.

import pytest

from adapter_ingestion.service.research import build_storage_namespace


def test_storage_namespace_composes_network_jurisdiction_sector_and_public_tenant_id() -> None:
    assert build_storage_namespace(
        network_kind="test-network",
        jurisdiction="CA-BC",
        sector="animal-research",
        tenant_id="7654321",
    ) == "test-network__ca-bc__animal-research__7654321"


@pytest.mark.parametrize("field", ["network_kind", "jurisdiction", "sector", "tenant_id"])
def test_storage_namespace_requires_every_isolation_dimension(field: str) -> None:
    values = {
        "network_kind": "test-network",
        "jurisdiction": "CA-BC",
        "sector": "animal-research",
        "tenant_id": "7654321",
    }
    values[field] = ""

    with pytest.raises(ValueError, match=field):
        build_storage_namespace(**values)
