# Flow contract: an XLSX workbook with the veterinary API-CONFIG marker exposes its software id and header mapping.
import unittest
from pathlib import Path
from adapter_ingestion.service.api_config import extract_embedded_api_config

class VeterinaryApiConfigTest(unittest.TestCase):
    def test_extract_embedded_api_config(self):
        xlsx_path = Path(__file__).resolve().parents[1] / "examples/research-search/research-search-veterinary-study-a.xlsx"
        extracted = extract_embedded_api_config(xlsx_path)
        self.assertIsNotNone(extracted)
        self.assertEqual(extracted["runtimeDefaults"]["softwareId"], "research-search-fixture-veterinary-study-a")
        self.assertEqual(extracted["schemaConfig"]["headerRowIndex"], 3)

if __name__ == "__main__":
    unittest.main()
