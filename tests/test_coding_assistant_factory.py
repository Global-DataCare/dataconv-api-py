# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.
# A configured terminology service always produces human-review candidates; model ranking is optional.

from __future__ import annotations

from types import SimpleNamespace

from adapter_ingestion.ai.terminology import TerminologyCodingAssistant
from adapter_ingestion.service.factory import build_coding_assistant


def test_factory_keeps_terminology_candidates_when_model_ranking_is_unavailable() -> None:
    settings = SimpleNamespace(
        terminology_base_url="http://terminology.local",
        terminology_token="token",
        terminology_timeout_seconds=15,
        coding_model_base_url="",
        coding_model_audience="",
        coding_model_token="",
        coding_model_id="",
        coding_model_timeout_seconds=30,
    )

    assistant = build_coding_assistant(settings, SimpleNamespace())

    assert isinstance(assistant, TerminologyCodingAssistant)
