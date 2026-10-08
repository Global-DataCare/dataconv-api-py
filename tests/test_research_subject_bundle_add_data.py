# Flow contract: one authorized direct document Bundle creates or extends exactly one study-bound ResearchSubject without Communication wrapping.
from __future__ import annotations

from types import SimpleNamespace

import pytest

from adapter_ingestion.runtime.adapters import InMemoryVaultRepository
from adapter_ingestion.runtime.adapters.search import InMemorySearchRepository
from adapter_ingestion.service.api_support import HTTPException
from adapter_ingestion.service.managers.research_subject_bundle import ResearchSubjectBundleManager
from adapter_ingestion.service.research import build_storage_namespace


SUBJECT_ID = "19740b0b-9413-47fa-a99c-f607ac784ad8"
STUDY = "ResearchStudy/veterinary-study-a"


def _manager():
    search = InMemorySearchRepository()
    vault = InMemoryVaultRepository()
    deps = SimpleNamespace(
        settings=SimpleNamespace(demo_mode=True, network_mode="test"),
        search_repo=search,
        vault_repo=vault,
    )
    return ResearchSubjectBundleManager(deps), search, vault


def _bundle(subject_id: str = SUBJECT_ID) -> dict:
    return {
        "resourceType": "Bundle",
        "type": "document",
        "entry": [
            {"resource": {
                "resourceType": "Composition",
                "status": "final",
                "subject": {"reference": f"ResearchSubject/{subject_id}"},
                "section": [{
                    "code": {"coding": [{"system": "http://loinc.org", "code": "11450-4"}]},
                    "entry": [{"reference": "Condition/condition-1"}],
                }],
            }},
            {"resource": {"resourceType": "ResearchSubject", "id": subject_id}},
            {"resource": {
                "resourceType": "Condition",
                "id": "condition-1",
                "meta": {"claims": {"Condition.code-text": "Fracture"}},
            }},
        ],
    }


def test_direct_bundle_creates_missing_twin_and_indexes_its_clinical_resource() -> None:
    manager, search, _vault = _manager()

    result = manager.handle_add_data(
        tenant_id="clinic-a", jurisdiction="ES", sector="onehealth-research",
        study=STUDY, request=SimpleNamespace(headers={}), body=_bundle(),
    )

    assert result["created"] is True
    assert result["researchSubject"]["id"] == SUBJECT_ID
    claims = result["researchSubject"]["meta"]["claims"]
    assert claims["ResearchSubject.identifier"] == f"urn:uuid:{SUBJECT_ID}"
    assert claims["ResearchSubject.study"] == STUDY
    vault_id = build_storage_namespace(
        network_kind="test", jurisdiction="ES", sector="onehealth-research", tenant_id="clinic-a",
    )
    condition = search.search(vault_id=vault_id, resource_type="Condition", search_params={})[0]
    assert condition["meta"]["claims"]["Condition.subject"] == f"urn:uuid:{SUBJECT_ID}"


def test_direct_bundle_generates_the_twin_uuid_when_the_composition_has_no_subject() -> None:
    manager, _search, _vault = _manager()
    bundle = _bundle()
    bundle["entry"][0]["resource"].pop("subject")
    bundle["entry"] = [entry for entry in bundle["entry"] if entry["resource"]["resourceType"] != "ResearchSubject"]

    result = manager.handle_add_data(
        tenant_id="clinic-a", jurisdiction="ES", sector="onehealth-research",
        study=STUDY, request=SimpleNamespace(headers={}), body=bundle,
    )

    assert result["created"] is True
    generated = result["researchSubject"]["id"]
    assert len(generated) == 36
    assert result["researchSubject"]["meta"]["claims"]["ResearchSubject.identifier"] == f"urn:uuid:{generated}"


def test_direct_bundle_extends_existing_twin_without_duplicate_resource() -> None:
    manager, _search, _vault = _manager()
    first = manager.handle_add_data(
        tenant_id="clinic-a", jurisdiction="ES", sector="onehealth-research",
        study=STUDY, request=SimpleNamespace(headers={}), body=_bundle(),
    )
    changed = _bundle()
    changed["entry"][2]["resource"]["meta"]["claims"]["Condition.code-text"] = "Closed fracture"

    second = manager.handle_add_data(
        tenant_id="clinic-a", jurisdiction="ES", sector="onehealth-research",
        study=STUDY, request=SimpleNamespace(headers={}), body=changed,
    )

    assert first["created"] is True
    assert second["created"] is False
    conditions = [
        item for item in second["researchSubject"]["contained"]
        if item.get("resourceType") == "Condition" and item.get("id") == "condition-1"
    ]
    assert len(conditions) == 1
    assert conditions[0]["meta"]["claims"]["Condition.code-text"] == "Closed fracture"


def test_direct_bundle_rejects_subject_already_bound_to_another_study() -> None:
    manager, _search, _vault = _manager()
    manager.handle_add_data(
        tenant_id="clinic-a", jurisdiction="ES", sector="onehealth-research",
        study=STUDY, request=SimpleNamespace(headers={}), body=_bundle(),
    )

    with pytest.raises(HTTPException) as error:
        manager.handle_add_data(
            tenant_id="clinic-a", jurisdiction="ES", sector="onehealth-research",
            study="ResearchStudy/veterinary-study-b", request=SimpleNamespace(headers={}), body=_bundle(),
        )
    assert error.value.status_code == 409
