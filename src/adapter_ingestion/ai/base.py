# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass

from ..models import CanonicalRecord


@dataclass(frozen=True)
class CodingSuggestion:
    system: str
    code: str
    display: str
    confidence: float
    evidence: str


class CodingAssistant:
    def suggest_codes(self, record: CanonicalRecord) -> list[CodingSuggestion]:
        raise NotImplementedError


class NoopCodingAssistant:
    def suggest_codes(self, record: CanonicalRecord) -> list[CodingSuggestion]:
        return []
