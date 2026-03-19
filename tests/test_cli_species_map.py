# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapter_ingestion.cli import _load_species_catalog, _load_species_local_map


class CliSpeciesMapTests(unittest.TestCase):
    def test_load_species_catalog_uses_static_codes(self) -> None:
        payload = {
            "system": "http://hl7.org/fhir/target-species",
            "codes": {
                "100000108988": "Dogs",
            },
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(payload, tmp, ensure_ascii=False)
            path = tmp.name
        try:
            system, catalog = _load_species_catalog(path)
            self.assertEqual(system, "http://hl7.org/fhir/target-species")
            self.assertEqual(catalog.get("100000108988"), "Dogs")
        finally:
            path_obj = Path(path)
            if path_obj.exists():
                path_obj.unlink()

    def test_loads_species_local_to_fhir_code(self) -> None:
        payload = {
            "speciesLocalToFhirCode": {
                "Perro": "100000108988",
                "Gato": "100000109056",
            }
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(payload, tmp, ensure_ascii=False)
            path = tmp.name
        try:
            mapping = _load_species_local_map(
                path,
            )
            self.assertEqual(mapping.get("Perro"), "100000108988")
            self.assertEqual(mapping.get("Gato"), "100000109056")
        finally:
            path_obj = Path(path)
            if path_obj.exists():
                path_obj.unlink()

    def test_rejects_legacy_local_to_fhir_code_key(self) -> None:
        payload = {
            "localToFhirCode": {
                "Perro": "100000108988",
            }
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(payload, tmp, ensure_ascii=False)
            path = tmp.name
        try:
            with self.assertRaises(ValueError):
                _load_species_local_map(
                    path,
                )
        finally:
            path_obj = Path(path)
            if path_obj.exists():
                path_obj.unlink()

    def test_rejects_legacy_fhir_code_to_local_key(self) -> None:
        payload = {
            "fhirCodeToLocal": {
                "100000108988": "Perro",
            }
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(payload, tmp, ensure_ascii=False)
            path = tmp.name
        try:
            with self.assertRaises(ValueError):
                _load_species_local_map(
                    path,
                )
        finally:
            path_obj = Path(path)
            if path_obj.exists():
                path_obj.unlink()


if __name__ == "__main__":
    unittest.main()
