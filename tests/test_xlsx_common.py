# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapter_ingestion.manufacturers.xlsx_common import (
    composition_section,
    parse_fhir_datetime,
    resolve_species_local,
    resolve_species_local_and_code,
)


class XlsxCommonTests(unittest.TestCase):
    def test_parse_spanish_long_date_and_time(self) -> None:
        value = parse_fhir_datetime("28 de Enero de 2026", "13:30")
        self.assertEqual(value, "2026-01-28T13:30:00Z")

    def test_parse_date_without_time_defaults_midnight(self) -> None:
        value = parse_fhir_datetime("2026-01-28", "")
        self.assertEqual(value, "2026-01-28T00:00:00Z")

    def test_species_contains_match_returns_local_value_only(self) -> None:
        species, code = resolve_species_local_and_code(
            "ZOE (Perro)",
            contains_rules=[{"contains": "Perro", "value": "Perro"}],
            fallback_to_source=False,
        )
        self.assertEqual(species, "Perro")
        self.assertIsNone(code)

    def test_species_contains_without_match_and_no_fallback(self) -> None:
        species = resolve_species_local(
            "FREYA",
            contains_rules=[{"contains": "Perro", "value": "Perro"}],
            fallback_to_source=False,
        )
        self.assertEqual(species, "")

    def test_composition_section_uses_normalized_section_family(self) -> None:
        value = composition_section("Clínica", "Vacunas")
        self.assertEqual(value, "clinica:vacunas")


if __name__ == "__main__":
    unittest.main()
