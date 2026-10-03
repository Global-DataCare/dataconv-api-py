# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from adapter_ingestion.ai.base import NoopCodingAssistant
from adapter_ingestion.manufacturers.registry import get_adapter
from adapter_ingestion.models import AdapterContext
from adapter_ingestion.pipeline import run_pipeline
from adapter_ingestion.research_search_workbooks import (
    FIXTURE_SUBJECT_UUID_BY_ORIGINAL_ID,
    RESEARCH_STUDY_A,
    VETERINARY_SUBJECTS,
    generate_research_search_workbooks,
)
from adapter_ingestion.runtime import PreconversionControlPlane
from adapter_ingestion.runtime.adapters import (
    InMemoryBlobStore,
    InMemoryConfigStore,
    InMemoryJobQueue,
    InMemoryJobStore,
    InMemorySearchRepository,
    InMemoryVaultRepository,
)
from adapter_ingestion.service.api_config import extract_embedded_api_config
from adapter_ingestion.service.job_processor import process_one_job
from adapter_ingestion.service.managers.research_bulk_export import ResearchBulkExportManager
from adapter_ingestion.service.research import build_storage_namespace
from adapter_ingestion.service.settings import ServiceSettings


def _subjects(path: Path) -> list[dict]:
    embedded = extract_embedded_api_config(path)
    assert embedded is not None
    context = AdapterContext(
        manufacturer="api-config", tenant_id="research-fixture", jurisdiction="ES",
        sector="onehealth-research", issuer_did="did:web:issuer.example",
        audience_did="did:web:audience.example", subject_did_prefix="urn:uuid",
        subject_kind=embedded["runtimeDefaults"]["subjectKind"], strict_species_mapping=False,
        data_use="secondary",
        personal_id_resolver=lambda original_id: FIXTURE_SUBJECT_UUID_BY_ORIGINAL_ID[str(original_id)],
        schema_config=embedded["schemaConfig"],
    )
    records = get_adapter("api-config").read_records(path, context)
    result = run_pipeline(records, context, NoopCodingAssistant())
    return [entry["resource"] for entry in result.composition_message["body"]["data"]]


def _manager(tmp_path: Path):
    generated = generate_research_search_workbooks(tmp_path)
    search = InMemorySearchRepository()
    vault = InMemoryVaultRepository()
    blobs = InMemoryBlobStore()
    control = PreconversionControlPlane(InMemoryConfigStore(), InMemoryJobStore(), InMemoryJobQueue())
    vault_id = build_storage_namespace(network_kind="test", jurisdiction="ES", sector="onehealth-research", tenant_id="fixture")
    subjects = _subjects(generated["veterinary-study-a"])
    for subject in subjects:
        subject["meta"]["claims"]["ResearchSubject.study"] = RESEARCH_STUDY_A
        search.upsert(vault_id=vault_id, resource_type="ResearchSubject", resource=subject)
    deps = SimpleNamespace(
        settings=SimpleNamespace(demo_mode=True, network_mode="test"), search_repo=search,
        vault_repo=vault, blob_store=blobs, control_plane=control,
    )
    return ResearchBulkExportManager(deps), control, blobs, vault


def test_creates_a_native_group_of_pseudonymous_patients_for_one_research_study(tmp_path: Path) -> None:
    manager, _, _, vault = _manager(tmp_path)
    group = manager.create_group(
        tenant_id="fixture", jurisdiction="ES", sector="onehealth-research",
        request=SimpleNamespace(headers={}),
        body={
            "resourceType": "Group", "type": "animal", "actual": True,
            "identifier": [{"value": RESEARCH_STUDY_A}],
            "member": [{"entity": {"reference": f"Patient/{identifier.removeprefix('urn:uuid:')}"}} for identifier in VETERINARY_SUBJECTS[:3]],
        },
    )

    assert group["resourceType"] == "Group"
    assert group["actual"] is True
    assert len(group["member"]) == 3
    assert all(member["entity"]["reference"].startswith("Patient/") for member in group["member"])
    stored = vault.get("test__es__onehealth-research__fixture", group["id"], "Group")
    assert stored is not None
    assert stored["meta"]["claims"]["Group.member"].startswith("Patient/")
    assert "member" not in stored


def test_rejects_research_subject_references_as_nonstandard_group_members(tmp_path: Path) -> None:
    manager, _, _, _ = _manager(tmp_path)
    with pytest.raises(Exception, match="Patient"):
        manager.create_group(
            tenant_id="fixture", jurisdiction="ES", sector="onehealth-research",
            request=SimpleNamespace(headers={}),
            body={
                "resourceType": "Group", "type": "animal", "actual": True,
                "identifier": [{"value": RESEARCH_STUDY_A}],
                "member": [{"entity": {"reference": f"ResearchSubject/{VETERINARY_SUBJECTS[0].removeprefix('urn:uuid:')}"}}],
            },
        )


def test_group_export_uses_async_content_location_and_type_separated_ndjson(tmp_path: Path) -> None:
    manager, control, blobs, _ = _manager(tmp_path)
    group = manager.create_group(
        tenant_id="fixture", jurisdiction="ES", sector="onehealth-research",
        request=SimpleNamespace(headers={}),
        body={
            "resourceType": "Group", "type": "animal", "actual": True,
            "identifier": [{"value": RESEARCH_STUDY_A}],
            "member": [{"entity": {"reference": f"Patient/{identifier.removeprefix('urn:uuid:')}"}} for identifier in VETERINARY_SUBJECTS[:2]],
        },
    )
    kickoff = manager.kickoff(
        tenant_id="fixture", jurisdiction="ES", sector="onehealth-research", group_id=group["id"],
        request=SimpleNamespace(headers={}), output_format="application/fhir+ndjson", resource_types=(),
    )
    assert kickoff["status"] == 202
    assert kickoff["contentLocation"].endswith(f"/bulk-status/{kickoff['jobId']}")

    settings = ServiceSettings(
        node_env="test", port=8080, host="127.0.0.1", db_provider="mem", search_provider="mem",
        queue_provider="mem", storage_provider="mem", local_data_dir=str(tmp_path), gcp_project_id="",
        gcp_region="europe-west1", firestore_config_collection="test-configs", firestore_job_collection="test-jobs",
        pubsub_topic_id="test-topic", pubsub_subscription_id="test-subscription", gcs_bucket_name="", gcs_prefix="",
        postgres_dsn="", postgres_search_table="resource_search_index",
        default_issuer_did="did:web:dataconv.example", default_audience_did="did:web:gw.example",
        default_subject_did_prefix="urn:uuid", default_species_fhir_file="",
        iclaims_app_id="test", iclaims_vertical="test", iclaims_locale="en", iclaims_code_domain="none",
        iclaims_inference_domain="none", auth_disabled_subjects=(), auth_disabled_devices=(), demo_mode=True,
        exchange_session_token_secret="test-only-secret", exchange_session_token_ttl_seconds=900,
        exchange_oidc_issuer="", exchange_oidc_audience="", exchange_oidc_allowed_issuers=(),
        exchange_oidc_allowed_audiences=(), exchange_oidc_jwks_cache_ttl_seconds=3600,
        exchange_default_allowed_scopes="dataconv.read", exchange_allow_insecure_assertions=True,
        exchange_allow_api_key=False, exchange_api_keys=(), exchange_api_key_subject_default="",
        exchange_api_key_org_default="", job_result_ttl_seconds=3600,
    )
    process_one_job(
        control_plane=control, blob_store=blobs, vault_repo=InMemoryVaultRepository(),
        settings=settings, worker_id="bulk-export-worker",
    )
    manifest = manager.status(
        tenant_id="fixture", jurisdiction="ES", sector="onehealth-research",
        job_id=kickoff["jobId"], request=SimpleNamespace(headers={}),
    )
    assert manifest["status"] == 200
    assert manifest["body"]["requiresAccessToken"] is True
    output = manifest["body"]["output"]
    assert {item["type"] for item in output} >= {
        "Patient", "ResearchSubject", "Composition", "DocumentReference", "Encounter",
        "Condition", "Immunization",
    }
    for item in output:
        assert item["url"].endswith(f"/{item['type']}.ndjson")
        payload = manager.download(
            tenant_id="fixture", jurisdiction="ES", sector="onehealth-research",
            job_id=kickoff["jobId"], resource_type=item["type"], request=SimpleNamespace(headers={}),
        )
        lines = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line]
        assert len(lines) == item["count"]
        assert all(resource["resourceType"] == item["type"] for resource in lines)
        assert all("claims" not in resource.get("meta", {}) for resource in lines)

    research_subjects = [
        json.loads(line) for line in manager.download(
            tenant_id="fixture", jurisdiction="ES", sector="onehealth-research", job_id=kickoff["jobId"],
            resource_type="ResearchSubject", request=SimpleNamespace(headers={}),
        ).decode("utf-8").splitlines()
    ]
    assert research_subjects[0]["individual"]["reference"].startswith("Patient/")
    assert research_subjects[0]["identifier"][0]["value"].startswith("urn:uuid:")

    compositions = [
        json.loads(line) for line in manager.download(
            tenant_id="fixture", jurisdiction="ES", sector="onehealth-research", job_id=kickoff["jobId"],
            resource_type="Composition", request=SimpleNamespace(headers={}),
        ).decode("utf-8").splitlines()
    ]
    assert compositions[0]["subject"]["reference"].startswith("Patient/")
    assert compositions[0]["section"][0]["entry"]
