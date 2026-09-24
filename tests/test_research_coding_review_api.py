# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.
# The HTTP contract exposes durable study review independently of conversion jobs.

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_http_search_returns_durable_pending_research_subjects() -> None:
    environment = {
        "NODE_ENV": "test",
        "HOST_INTERNAL_IP": "127.0.0.1",
        "PORT": "8080",
        "DB_PROVIDER": "mem",
        "SEARCH_PROVIDER": "mem",
        "QUEUE_PROVIDER": "mem",
        "STORAGE_PROVIDER": "mem",
        "NETWORK_KIND": "test",
        "PRECONV_LOCAL_DATA_DIR": str(ROOT / "artifacts" / "test-runtime"),
        "PRECONV_DEFAULT_SPECIES_FHIR_FILE": str(
            ROOT / "configs" / "fhir-target-species.template.editable.json"
        ),
        "ICLAIMS_APP_ID": "vet-claims-api",
        "ICLAIMS_VERTICAL": "vet",
        "ICLAIMS_LOCALE": "es",
        "ICLAIMS_CODE_DOMAIN": "none",
        "ICLAIMS_INFERENCE_DOMAIN": "none",
        "DEMO_MODE": "true",
    }
    with patch.dict(os.environ, environment, clear=False):
        sys.modules.pop("adapter_ingestion.service.api", None)
        service_api = importlib.import_module("adapter_ingestion.service.api")
        app = importlib.reload(service_api).create_app()
        vault_id = "test__ca-bc__animal-research__research-tenant"
        app.state.vault_repo.put(vault_id, [{
            "resourceType": "ResearchSubject",
            "id": "subject-1",
            "meta": {"claims": {
                "ResearchSubject.study": "ResearchStudy/study-http-review",
            }},
            "contained": [{
                "resourceType": "Condition",
                "id": "condition-1",
                "meta": {"codingProposals": [{
                    "id": "proposal-1",
                    "status": "proposed",
                    "field": "Condition.code",
                    "inputText": "otitis",
                    "rowContext": {},
                    "candidates": [],
                }]},
            }],
        }], "ResearchSubject")

        response = TestClient(app).post(
            "/publisher/cds-CA-BC/v1/animal-research/research-tenant/dataset/ResearchSubject/$review-pending",
            headers={"Authorization": "Bearer demo-token"},
            json={
                "resourceType": "Parameters",
                "parameter": [{
                    "name": "study",
                    "valueReference": {"reference": "ResearchStudy/study-http-review"},
                }],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["entry"][0]["resource"]["contained"][0]["meta"]["codingProposals"][0]["id"] == "proposal-1"
