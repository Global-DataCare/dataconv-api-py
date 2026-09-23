# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.
# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest
from types import SimpleNamespace
from pathlib import Path
import sys
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapter_ingestion.runtime import JobRequest, PreconversionControlPlane
from adapter_ingestion.runtime.adapters import (
    InMemoryBlobStore,
    InMemoryConfigStore,
    InMemoryJobQueue,
    InMemoryJobStore,
    InMemorySearchRepository,
    InMemoryVaultRepository,
)
from adapter_ingestion.service.managers.dependencies import ApiManagerDependencies
from adapter_ingestion.service.managers.conversion_patch import ConversionPatchManager
from adapter_ingestion.service.settings import ServiceSettings


class RecordingFeedbackSink:
    def __init__(self) -> None:
        self.events = []

    def submit(self, event) -> None:
        self.events.append(event)


class TestConversionPatchManager(unittest.TestCase):
    def test_handle_saves_progress_and_promotes_only_after_every_proposal_is_resolved(self) -> None:
        # Each PATCH saves one explicit human decision. The final twin remains
        # outside the search repository until every contained proposal is resolved.
        vault_repo = InMemoryVaultRepository()
        search_repo = InMemorySearchRepository()
        vault_id = "test__es__onehealth-research__test-tenant-123"
        study_reference = "ResearchStudy/study-review-1"
        control_plane = PreconversionControlPlane(
            config_store=InMemoryConfigStore(),
            job_store=InMemoryJobStore(),
            job_queue=InMemoryJobQueue(),
        )
        control_plane.submit_job(JobRequest(
            alternate_name="test-tenant-123",
            manufacturer="test",
            manufacturer_version="v1.0",
            sector="onehealth-research",
            country="ES",
            thid="test-thid-123",
            research_study_reference=study_reference,
        ))
        
        # Insert a Composition that points to an Encounter
        composition = {
            "resourceType": "Composition",
            "id": "comp-1",
            "meta": {
                "claims": {
                    "Composition.relatesto-target": "test-thid-123",
                    "Composition.userSelected": "true",
                    "Composition.subject": "Patient:pat-1",
                    "Composition.section": "tests|sec-1",
                    "Composition.entry": "Encounter:enc-1"
                }
            }
        }
        vault_repo.put(vault_id, [composition], "Composition")

        research_subject = {
            "resourceType": "ResearchSubject",
            "id": "pat-1",
            "meta": {
                "claims": {
                    "ResearchSubject.identifier": "urn:uuid:pat-1",
                    "ResearchSubject.status": "candidate",
                    "ResearchSubject.userSelected": "true",
                    "ResearchSubject.study": study_reference,
                }
            },
        }
        vault_repo.put(vault_id, [research_subject], "ResearchSubject")
        
        # Insert the actual target resource
        encounter = {
            "resourceType": "Encounter",
            "id": "enc-1",
            "meta": {
                "claims": {
                    "Encounter.userSelected": "true"
                }
            }
        }
        vault_repo.put(vault_id, [encounter], "Encounter")
        
        # Insert the linkage (it's what tells us that enc-1 is an Encounter)
        link = {
            "id": "enc-1",
            "resourceType": "Encounter"
        }
        vault_repo.put(vault_id, [link], "pat-1_sec-1")

        condition = {
            "resourceType": "Condition",
            "id": "condition-1",
            "meta": {
                "claims": {"Condition.userSelected": "true"},
                "codingProposals": [{
                    "id": "proposal-1",
                    "status": "proposed",
                    "field": "Condition.code",
                    "inputText": "otitis",
                    "rowContext": {"species": "canine", "symptoms": "recurrent discharge"},
                    "candidates": [
                        {
                            "id": "candidate-media",
                            "system": "http://snomed.info/sct",
                            "code": "3135009",
                            "display": "Otitis media",
                            "recommendationPercent": 56.0,
                        },
                        {
                            "id": "candidate-externa",
                            "system": "http://snomed.info/sct",
                            "code": "129127001",
                            "display": "Otitis externa",
                            "recommendationPercent": 44.0,
                        },
                    ],
                }],
            },
        }
        vault_repo.put(vault_id, [condition], "Condition")
        vault_repo.put(vault_id, [{"id": "condition-1", "resourceType": "Condition"}], "pat-1_sec-1")
        immunization = {
            "resourceType": "Immunization",
            "id": "immunization-1",
            "meta": {
                "claims": {"Immunization.vaccine-code-text": "rabia"},
                "codingProposals": [{
                    "id": "proposal-immunization-1",
                    "status": "proposed",
                    "field": "Immunization.vaccine-code",
                    "inputText": "rabia",
                    "rowContext": {"species": "canine"},
                    "candidates": [{
                        "id": "candidate-rabies",
                        "system": "http://www.whocc.no/atcvet",
                        "code": "QI07AA02",
                        "display": "Rabies virus, inactivated",
                    }],
                }],
            },
        }
        vault_repo.put(vault_id, [immunization], "Immunization")
        vault_repo.put(vault_id, [{"id": "immunization-1", "resourceType": "Immunization"}], "pat-1_sec-1")
        composition["meta"]["claims"]["Composition.entry"] = (
            "Encounter:enc-1,Condition:condition-1,Immunization:immunization-1"
        )
        vault_repo.put(vault_id, [composition], "Composition")

        completed_composition = {
            "resourceType": "Composition",
            "id": "comp-2",
            "meta": {"claims": {
                "Composition.relatesto-target": "test-thid-123",
                "Composition.subject": "Patient:pat-2",
                "Composition.section": "tests|sec-2",
                "Composition.entry": "Encounter:enc-2",
            }},
        }
        completed_subject = {
            "resourceType": "ResearchSubject",
            "id": "pat-2",
            "meta": {"claims": {
                "ResearchSubject.identifier": "urn:uuid:pat-2",
                "ResearchSubject.status": "candidate",
                "ResearchSubject.study": study_reference,
            }},
        }
        completed_encounter = {
            "resourceType": "Encounter",
            "id": "enc-2",
            "meta": {"claims": {"Encounter.identifier": "urn:uuid:enc-2"}},
        }
        vault_repo.put(vault_id, [completed_composition], "Composition")
        vault_repo.put(vault_id, [completed_subject], "ResearchSubject")
        vault_repo.put(vault_id, [completed_encounter], "Encounter")
        vault_repo.put(vault_id, [{"id": "enc-2", "resourceType": "Encounter"}], "pat-2_sec-2")

        feedback_sink = RecordingFeedbackSink()
        
        deps = ApiManagerDependencies(
            settings=ServiceSettings(
                node_env="test",
                port=8080,
                host="127.0.0.1",
                db_provider="mem",
                search_provider="mem",
                queue_provider="mem",
                storage_provider="mem",
                local_data_dir=str(ROOT / "artifacts" / "test-runtime"),
                gcp_project_id="",
                gcp_region="europe-west1",
                firestore_config_collection="test-configs",
                firestore_job_collection="test-jobs",
                pubsub_topic_id="test-topic",
                pubsub_subscription_id="test-subscription",
                gcs_bucket_name="",
                gcs_prefix="",
                postgres_dsn="",
                postgres_search_table="resource_search_index",
                default_issuer_did="did:web:globaldatacare.es:employee:preconversion",
                default_audience_did="did:web:globaldatacare.es",
                default_subject_did_prefix="did:web:globaldatacare.es",
                default_species_fhir_file=str(ROOT / "configs" / "fhir-target-species.template.editable.json"),
                iclaims_app_id="app",
                iclaims_vertical="vet",
                iclaims_locale="es",
                iclaims_code_domain="none",
                iclaims_inference_domain="none",
                auth_disabled_subjects=(),
                auth_disabled_devices=(),
                demo_mode=True,
                exchange_session_token_secret="dev-session-secret-change-me",
                exchange_session_token_ttl_seconds=900,
                exchange_oidc_issuer="",
                exchange_oidc_audience="",
                exchange_oidc_allowed_issuers=(),
                exchange_oidc_allowed_audiences=(),
                exchange_oidc_jwks_cache_ttl_seconds=3600,
                exchange_default_allowed_scopes="dataconv.upload",
                exchange_allow_insecure_assertions=True,
                exchange_allow_api_key=False,
                exchange_api_keys=(),
                exchange_api_key_subject_default="",
                exchange_api_key_org_default="",
                job_result_ttl_seconds=3600,
            ),
            control_plane=control_plane,
            blob_store=InMemoryBlobStore(),
            vault_repo=vault_repo,
            search_repo=search_repo,
            config_create_responses={},
            coding_feedback_sink=feedback_sink,
        )
        manager = ConversionPatchManager(deps)
        
        body = {
            "type": "https://didcomm.org/plaintext/2.0/message",
            "iss": "did:web:example.org:employee:demo",
            "iat": 1000,
            "exp": 2000,
            "thid": "test-thid-123",
            "researchStudy": {"reference": study_reference},
            "body": {
                "codingReviews": [{
                    "resourceType": "Condition",
                    "resourceId": "condition-1",
                    "proposalId": "proposal-1",
                    "selectedCandidateId": "candidate-externa",
                    "reason": "Otoscopy localized inflammation to the external canal",
                }]
            },
        }
        
        request = SimpleNamespace(headers={})
        with self.assertRaises(HTTPException) as wrong_tenant:
            manager.handle(
                tenant_id="another-tenant",
                jurisdiction="es",
                sector="onehealth-research",
                software_id="test-v1.0",
                resource_type="Composition",
                response=SimpleNamespace(),
                request=request,
                body={key: value for key, value in body.items() if key != "researchStudy"},
            )
        self.assertEqual(getattr(wrong_tenant.exception, "status_code", None), 404)

        with self.assertRaises(HTTPException) as wrong_software:
            manager.handle(
                tenant_id="test-tenant-123",
                jurisdiction="es",
                sector="onehealth-research",
                software_id="another-v1.0",
                resource_type="Composition",
                response=SimpleNamespace(),
                request=request,
                body={key: value for key, value in body.items() if key != "researchStudy"},
            )
        self.assertEqual(getattr(wrong_software.exception, "status_code", None), 404)

        with self.assertRaises(HTTPException) as mismatch:
            manager.handle(
                tenant_id="test-tenant-123",
                jurisdiction="es",
                sector="onehealth-research",
                software_id="test-v1.0",
                resource_type="Composition",
                response=SimpleNamespace(),
                request=request,
                body={
                    **body,
                    "researchStudy": {"reference": "ResearchStudy/another-study"},
                },
            )
        self.assertEqual(getattr(mismatch.exception, "status_code", None), 404)

        res = manager.handle(
            tenant_id="test-tenant-123",
            jurisdiction="es",
            sector="onehealth-research",
            software_id="test-v1.0",
            resource_type="Composition",
            response=SimpleNamespace(),
            request=request,
            body=body
        )
        
        self.assertEqual(res["body"]["status"], "pending-review")
        self.assertEqual(res["body"]["promotedCount"], 3)
        self.assertEqual(res["body"]["pendingSubjectCount"], 1)
        self.assertEqual(res["body"]["pendingProposalCount"], 1)
        self.assertEqual(res["body"]["issues"]["resourceType"], "OperationOutcome")
        self.assertEqual(res["body"]["issues"]["issue"][0]["severity"], "information")
        self.assertNotIn("publication", res["body"])
        self.assertGreaterEqual(len(res["body"]["data"]), 1)
        
        # Verify changes in Vault
        indexed_comp = search_repo.search(
            vault_id=vault_id,
            resource_type="Composition",
            search_params={"relatesto-target": "test-thid-123"},
        )
        indexed_enc = search_repo.search(
            vault_id=vault_id,
            resource_type="Encounter",
            search_params={"userSelected": "false"},
        )
        indexed_research_subject = search_repo.search(
            vault_id=vault_id,
            resource_type="ResearchSubject",
            search_params={"identifier": "urn:uuid:pat-1"},
        )
        self.assertEqual([resource["id"] for resource in indexed_comp], ["comp-2"])
        self.assertEqual(indexed_enc, [])
        self.assertEqual(indexed_research_subject, [])
        self.assertEqual(len(search_repo.search(
            vault_id=vault_id,
            resource_type="ResearchSubject",
            search_params={"identifier": "urn:uuid:pat-2"},
        )), 1)
        promoted_condition = vault_repo.get(vault_id, "condition-1", "Condition")
        self.assertEqual(
            promoted_condition["meta"]["claims"]["Condition.code"],
            "http://snomed.info/sct|129127001",
        )
        self.assertEqual(
            promoted_condition["meta"]["claims"]["Condition.code-display"],
            "Otitis externa",
        )
        self.assertEqual(promoted_condition["meta"]["claims"]["Condition.userSelected"], "true")
        self.assertEqual(feedback_sink.events[0]["reason"], "Otoscopy localized inflammation to the external canal")

        final_body = {
            **body,
            "body": {
                "codingReviews": [{
                    "resourceType": "Immunization",
                    "resourceId": "immunization-1",
                    "proposalId": "proposal-immunization-1",
                    "selectedCandidateId": "candidate-rabies",
                }],
            },
        }
        final = manager.handle(
            tenant_id="test-tenant-123",
            jurisdiction="es",
            sector="onehealth-research",
            software_id="test-v1.0",
            resource_type="Composition",
            response=SimpleNamespace(),
            request=request,
            body=final_body,
        )

        self.assertEqual(final["body"]["status"], "success")
        self.assertGreaterEqual(final["body"]["promotedCount"], 5)
        promoted_immunization = vault_repo.get(vault_id, "immunization-1", "Immunization")
        self.assertEqual(
            promoted_immunization["meta"]["claims"]["Immunization.vaccine-code"],
            "http://www.whocc.no/atcvet|QI07AA02",
        )
        self.assertEqual(
            promoted_immunization["meta"]["claims"]["Immunization.vaccine-code-display"],
            "Rabies virus, inactivated",
        )
        self.assertEqual(
            promoted_immunization["meta"]["claims"]["Immunization.userSelected"],
            "true",
        )
        self.assertEqual(
            vault_repo.get(vault_id, "comp-1", "Composition")["meta"]["claims"]["Composition.userSelected"],
            "true",
        )
        self.assertEqual(len(search_repo.search(
            vault_id=vault_id,
            resource_type="ResearchSubject",
            search_params={"identifier": "urn:uuid:pat-1"},
        )), 1)

if __name__ == "__main__":
    unittest.main()
