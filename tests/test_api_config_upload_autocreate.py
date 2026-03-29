import unittest
from pathlib import Path
from adapter_ingestion.service.api_config import extract_embedded_api_config
from adapter_ingestion.service.managers.conversion_upload import ConversionUploadManager
from types import SimpleNamespace

class DummyBlobStore:
    def __init__(self, file_bytes):
        self._file_bytes = file_bytes
    def get_bytes(self, ref):
        return self._file_bytes
    def put_bytes(self, path, payload, content_type):
        return "dummy-ref"

class DummyControlPlane:
    def __init__(self):
        self.configs = {}
    def resolve_config(self, key):
        return self.configs.get(str(key), None)
    def upsert_config(self, key, content, updated_by):
        self.configs[str(key)] = SimpleNamespace(content=content)
    def submit_job(self, job_request):
        return SimpleNamespace(job_id="job-1")

class DummyDeps:
    class Settings:
        def __init__(self, sector):
            # sector: 'animal-care', 'human', etc.
            if sector == "animal-care":
                self.default_species_fhir_file = str(Path("configs/fhir-target-species.template.editable.json").absolute())
            else:
                self.default_species_fhir_file = None
            # Atributos dummy requeridos por default_tenant_config_payload
            self.default_subject_did_prefix = "did:example:subject:"
            self.default_issuer_did = "did:example:issuer"
            self.default_audience_did = "did:example:audience"
    def __init__(self, file_bytes, sector="animal-care"):
        self.blob_store = DummyBlobStore(file_bytes)
        self.control_plane = DummyControlPlane()
        self.settings = self.Settings(sector)

class TestApiConfigUploadAutoCreate(unittest.TestCase):
    def test_upload_creates_config_from_embedded(self):
        # Cargar bytes del Excel real
        xlsx_path = Path("/Users/fernando/GITS/gdc-workspace/examples/veterinary-api-config_datos_patologias.xlsx")
        file_bytes = xlsx_path.read_bytes()
        # Probar tanto con sector conocido como desconocido
        for sector in ("animal-care", "human"):  # "human" simula sector sin speciesFhir
            deps = DummyDeps(file_bytes, sector=sector)
            manager = ConversionUploadManager(deps)
            import asyncio
            async def run():
                await manager.handle(
                    tenant_id="acme",
                    jurisdiction="es",
                    sector=sector,
                    software_id="api-config",
                    resource_type="excel",
                    request=SimpleNamespace(headers={}, form=lambda: {}),
                    response=SimpleNamespace(headers={}),
                    file=None,
                    body={
                        "iss": "did:web:test.example:employee:loader",
                        "type": "https://didcomm.org/plaintext/2.0/message",
                        "iat": 1760000000,
                        "exp": 1760003600,
                        "thid": "job-test-001",
                        "inputRef": "dummy-ref",
                    },
                )
            asyncio.run(run())
            # Verificar que se creó la config para el softwareId embebido
            found = False
            for k, v in deps.control_plane.configs.items():
                if v.content.get("runtimeDefaults", {}).get("softwareId") == "veterinary-tabla_patologias":
                    found = True
                    # Si sector no tiene speciesFhir, debe estar presente pero vacío (codes: {})
                    if sector != "animal-care":
                        sf = v.content.get("speciesFhir", {})
                        self.assertTrue(
                            isinstance(sf, dict) and (not sf.get("codes")),
                            f"speciesFhir debe estar vacío (codes: {{}}) si el sector no lo define, actual: {sf}"
                        )
            self.assertTrue(found, f"No se creó la configuración automática para el softwareId embebido en sector {sector}")

if __name__ == "__main__":
    unittest.main()
