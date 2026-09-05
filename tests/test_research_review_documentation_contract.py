# Flow contract: document the human-reviewed research lifecycle and never represent AI coding proposals as approved data.
# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE_MARKER = "GCS -> Firestore draft -> human review -> PostgreSQL search index"


def test_high_level_docs_and_skill_preserve_the_review_storage_boundary() -> None:
    documented_contracts = [
        ROOT / "README.md",
        ROOT / "docs" / "en" / "09-storage-and-job-queue-adapters.md",
        ROOT / "docs" / "es" / "09-storage-y-job-queue-adapters.md",
        ROOT / ".codex" / "skills" / "preserve-fhir-flat-claim-boundaries" / "SKILL.md",
    ]

    for contract_path in documented_contracts:
        content = contract_path.read_text(encoding="utf-8")
        assert LIFECYCLE_MARKER in content, contract_path
        assert "NoopCodingAssistant" in content, contract_path
        assert "human-reviewed" in content, contract_path
        assert "ValueSet/$expand?filter=" in content, contract_path
        assert "ValueSet/$validate-code" in content, contract_path
        assert "ConceptMap/$translate" in content, contract_path
