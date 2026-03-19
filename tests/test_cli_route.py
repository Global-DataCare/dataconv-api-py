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

from adapter_ingestion.cli import _resource_route


class CliRouteTests(unittest.TestCase):
    def test_route_without_optional_segments_uses_prefix(self) -> None:
        route = _resource_route(
            resource_type="Composition",
            tenant_id="",
            jurisdiction="",
            sector="",
            route_prefix="/v1",
        )
        self.assertEqual(route, "/v1/individual/org.hl7.fhir.r4/Composition/_batch")

    def test_route_without_prefix_falls_back_to_root(self) -> None:
        route = _resource_route(
            resource_type="Composition",
            tenant_id="",
            jurisdiction="",
            sector="",
            route_prefix="",
        )
        self.assertEqual(route, "/individual/org.hl7.fhir.r4/Composition/_batch")

    def test_route_with_optional_segments_uses_segmented_shape(self) -> None:
        route = _resource_route(
            resource_type="Composition",
            tenant_id="acme",
            jurisdiction="es",
            sector="health-care",
            route_prefix="/v1",
        )
        self.assertEqual(
            route,
            "/acme/cds-es/v1/health-care/individual/org.hl7.fhir.r4/Composition/_batch",
        )


if __name__ == "__main__":
    unittest.main()
