# Test para extraer configuración embebida de veterinary-api-config_datos_patologias.xlsx
import unittest
from pathlib import Path
from adapter_ingestion.service.api_config import extract_embedded_api_config

class VeterinaryApiConfigTest(unittest.TestCase):
    def test_extract_embedded_api_config(self):
        xlsx_path = Path("/Users/fernando/GITS/gdc-workspace/examples/veterinary-api-config_datos_patologias.xlsx")
        extracted = extract_embedded_api_config(xlsx_path)
        print("EXTRACTED:", extracted)
        self.assertIsNotNone(extracted, "No se pudo extraer configuración embebida del Excel")
        self.assertIn("runtimeDefaults", extracted)
        self.assertIn("softwareId", extracted["runtimeDefaults"])  # Debe estar presente softwareId

if __name__ == "__main__":
    unittest.main()
