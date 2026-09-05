# Flow contract: reuse canonical claim catalogs; keep API-CONFIG logical fields separate from database keys.
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
from adapter_ingestion.service.routes_system import register_system_routes
from adapter_ingestion.manufacturers.registry import get_adapter


class ApiConfigTests(unittest.TestCase):
    APPMYPETS_EXAMPLE = ROOT.parent / "examples" / "AppMyPets-api-config.xlsx"

    def test_extract_embedded_api_config_from_csv(self) -> None:
        csv_text = (
            "API-CONFIG\n"
            ",date,concept,subject_id,section,family,subfamily,especies,appointment-lastoccurrencedate\n"
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
        self.assertEqual(extracted["schemaConfig"]["fieldMap"]["subject_id"], "CHIP")
        self.assertEqual(extracted["schemaConfig"]["fieldMap"]["species"], "ESPECIE")
        self.assertEqual(
            extracted["schemaConfig"]["fieldMap"]["appointment-lastoccurrencedate"],
            "ULTIMA VISITA",
        )

    def test_extract_embedded_api_config_accepts_marker_metadata_and_runtime_defaults(self) -> None:
        csv_text = (
            "API-CONFIG;language=es\n"
            ",subject_id,subject_animal-species,subject_animal-breeds,subject_animal-genderstatus,date\n"
            "tenant,_id,specie,breed,issterilized,createdat\n"
            "1,dog,westie,False,2026-03-01\n"
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
        self.assertEqual(extracted["runtimeDefaults"]["language"], "es")
        self.assertEqual(extracted["schemaConfig"]["fieldMap"]["subject_id"], "_id")
        self.assertEqual(extracted["schemaConfig"]["fieldMap"]["species"], "specie")
        self.assertEqual(extracted["schemaConfig"]["fieldMap"]["breed"], "breed")
        self.assertEqual(extracted["schemaConfig"]["fieldMap"]["genderStatus"], "issterilized")

    def test_extract_embedded_api_config_accepts_colon_marker_and_software_id(self) -> None:
        csv_text = (
            "API-CONFIG:language=es:software-id:qvet-v1\n"
            ",subject_id,subject_animal-species,subject_animal-breeds,subject_animal-genderstatus,date\n"
            "tenant,_id,specie,breed,issterilized,createdat\n"
            "1,dog,westie,False,2026-03-01\n"
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
        self.assertEqual(extracted["runtimeDefaults"]["language"], "es")
        self.assertEqual(extracted["runtimeDefaults"]["softwareId"], "qvet-v1")
        self.assertEqual(extracted["schemaConfig"]["fieldMap"]["subject_id"], "_id")
        self.assertEqual(extracted["schemaConfig"]["fieldMap"]["species"], "specie")
        self.assertEqual(extracted["schemaConfig"]["fieldMap"]["breed"], "breed")
        self.assertEqual(extracted["schemaConfig"]["fieldMap"]["genderStatus"], "issterilized")

    def test_api_config_adapter_keeps_qvet_loinc_defaults(self) -> None:
        adapter = get_adapter("api-config")
        self.assertEqual(adapter.default_loinc_overrides.get("clinica:consultas"), "34109-9")

    def test_well_known_api_config_exposes_supported_field_descriptions(self) -> None:
        class _App:
            def __init__(self) -> None:
                self.routes: dict[str, object] = {}

            def get(self, path: str, **_kwargs):  # type: ignore[no-untyped-def]
                def _decorator(func):
                    self.routes[path] = func
                    return func

                return _decorator

        class _Settings:
            iclaims_app_id = "preconvert-api"
            iclaims_vertical = "onehealth"
            iclaims_locale = "es"
            iclaims_code_domain = "none"
            iclaims_inference_domain = "none"
            default_issuer_did = "did:web:example.org:employee:preconversion"
            default_audience_did = "did:web:example.org"
            default_subject_did_prefix = "did:web:example.org"
            default_species_fhir_file = str(ROOT / "configs" / "fhir-target-species.template.editable.json")
            supported_jurisdictions = ("ES", "PT")
            supported_sectors = ("onehealth-research", "animal-care")
            exchange_allow_api_key = True

        app = _App()
        settings = _Settings()
        register_system_routes(app, settings)
        payload = app.routes["/.well-known/api-config.json"]()
        self.assertEqual(
            payload["supportedFields"]["section"],
            "Departamento o sección: tienda, clínica, farmacia, etc. (service-reference)",
        )
        self.assertEqual(
            payload["pendingFields"]["coverage_insurer"],
            "A name is not a safe Coverage.payor reference.",
        )
        self.assertEqual(
            payload["pendingFields"]["procedure_followup-date"],
            "No canonical Procedure search claim exists.",
        )
        self.assertEqual(
            payload["pendingFields"]["procedure_subpotent-date"],
            "No canonical Procedure search claim exists.",
        )
        self.assertEqual(
            payload["pendingFields"]["procedure_target-display"],
            "Requires a governed coded target.",
        )
        self.assertEqual(
            payload["supportedFields"]["DiagnosticReport.code-text"],
            "Nombre o diagnóstico local sin código terminológico",
        )
        self.assertEqual(
            payload["supportedFields"]["ChargeItem.supporting-information"],
            "Supporting Invoice reference; never encoded as ChargeItem.part-of",
        )
        self.assertEqual(
            payload["fieldAliases"]["invoice_date"],
            "Invoice.date",
        )
        self.assertEqual(payload["language"], "es")
        self.assertEqual(payload["allowedJurisdictions"], ["ES", "PT"])
        self.assertEqual(payload["allowedSectors"], ["onehealth-research", "animal-care"])
        self.assertEqual(payload["auth"]["exchangeEndpoint"], "/exchange")
        self.assertEqual(payload["auth"]["apiKeySupported"], True)
        self.assertEqual(
            payload["endpoints"]["upload"],
            "/host/cds-{jurisdiction}/v1/{sector}/{tenant_id}/{software_id}/config/_upload",
        )
        self.assertNotIn("schemaConfig", payload)
        self.assertNotIn("runtimeDefaults", payload)
        self.assertNotIn("apiConfig", payload)

    @unittest.skipUnless(APPMYPETS_EXAMPLE.exists(), "Local AppMyPets example not available")
    def test_extract_embedded_api_config_from_local_appmypets_example(self) -> None:
        extracted = extract_embedded_api_config(self.APPMYPETS_EXAMPLE)

        self.assertIsNotNone(extracted)
        self.assertEqual(extracted["runtimeDefaults"]["language"], "es")
        self.assertEqual(extracted["schemaConfig"]["headerRowIndex"], 3)

        field_map = extracted["schemaConfig"]["fieldMap"]
        self.assertEqual(field_map["subject_id"], "_id")
        self.assertEqual(field_map["species"], "specie")
        self.assertEqual(field_map["breed"], "breed")
        self.assertEqual(field_map["observation_weight"], "weight")
        self.assertEqual(field_map["procedure_code-display"], "petidvaccinestatus")
        self.assertEqual(field_map["procedure-subpotent-date"], "vaccineexpirationdate")
        self.assertEqual(field_map["coverage_insurer"], "insurancecompany")
        self.assertEqual(field_map["coverage_period-end"], "insuranceexpirationdate")
