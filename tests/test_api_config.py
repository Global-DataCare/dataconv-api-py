# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapter_ingestion.service.api_config import extract_embedded_api_config


class ApiConfigTests(unittest.TestCase):
    def test_extract_embedded_api_config_from_csv(self) -> None:
        csv_text = (
            "API-CONFIG\n"
            ",date,concept,subjectId,section,family,subfamily,especies,appointment-lastoccurrencedate\n"
            "EMPRESA,FECHA,CONCEPTO,CHIP,SECCION,FAMILIA,SUBFAMILIA,ESPECIE,ULTIMA VISITA\n"
            "Esteveter,2026-03-01,Consulta,123,clinica,consultas,CONSULTAS,CANINA,2026-03-02\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
            tmp.write(csv_text)
            tmp_path = Path(tmp.name)
        try:
            extracted = extract_embedded_api_config(tmp_path)
        finally:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass

        self.assertIsNotNone(extracted)
        self.assertEqual(extracted["schemaConfig"]["headerRowIndex"], 3)
        self.assertEqual(extracted["schemaConfig"]["fieldMap"]["date"], "FECHA")
        self.assertEqual(extracted["schemaConfig"]["fieldMap"]["subjectId"], "CHIP")
        self.assertEqual(extracted["schemaConfig"]["fieldMap"]["species"], "ESPECIE")
        self.assertEqual(
            extracted["schemaConfig"]["fieldMap"]["appointment-lastoccurrencedate"],
            "ULTIMA VISITA",
        )
