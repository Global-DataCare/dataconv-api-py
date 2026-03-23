# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
import tempfile
import sys
from tempfile import NamedTemporaryFile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapter_ingestion.models import AdapterContext
from adapter_ingestion.manufacturers.tabular_xlsx import TabularXlsxAdapter
from adapter_ingestion.manufacturers.wakyma import WakymaAdapter
from adapter_ingestion.manufacturers.xlsx_common import ParsedRow


class TabularXlsxTests(unittest.TestCase):
    def test_include_fields_supports_plus_join(self) -> None:
        adapter = WakymaAdapter()
        row = {
            "Tipo": "Consulta",
            "Motivo": "Revisión",
            "Fecha": "28 de Enero de 2026",
            "Hora": "13:30",
            "ID Interno Paciente": "123",
        }
        include_fields = ("TIPO", "MOTIVO", "FECHA+HORA")

        attributes = adapter._build_attributes(row=row, include_fields=include_fields)

        self.assertEqual(attributes.get("Tipo"), "Consulta")
        self.assertEqual(attributes.get("Motivo"), "Revisión")
        self.assertEqual(attributes.get("Fecha+Hora"), "28 de Enero de 2026 13:30")

    def test_loinc_override_fallback_to_section_wildcard(self) -> None:
        adapter = WakymaAdapter()
        code = adapter._resolve_loinc_code_for_record(
            section="clinica",
            family="otros",
            overrides={
                "clinica:*": "47045-0",
            },
        )
        self.assertEqual(code, "47045-0")

    def test_subject_id_hashes_non_multibase_internal_id(self) -> None:
        adapter = WakymaAdapter()
        context = AdapterContext(
            manufacturer="wakyma",
            tenant_id="acme",
            jurisdiction="es",
            sector="veterinary",
            issuer_did="did:web:acme.globaldatacare.es:employee:loader",
            audience_did="did:web:acme.globaldatacare.es",
            subject_did_prefix="did:web:acme.globaldatacare.es",
        )

        subject_id = adapter._subject_id(context=context, subject_token="123456", species_code="100000108988")

        self.assertIsNotNone(subject_id)
        self.assertTrue(subject_id.startswith("did:web:acme.globaldatacare.es:animal:subject:z"))
        self.assertNotIn(":subject:123456", subject_id)

    def test_subject_id_keeps_existing_multibase_token(self) -> None:
        adapter = WakymaAdapter()
        context = AdapterContext(
            manufacturer="wakyma",
            tenant_id="acme",
            jurisdiction="es",
            sector="veterinary",
            issuer_did="did:web:acme.globaldatacare.es:employee:loader",
            audience_did="did:web:acme.globaldatacare.es",
            subject_did_prefix="did:web:acme.globaldatacare.es",
        )

        token_multibase = "zQmWATW6YwRbc2Qfq5Qv7FpC18JNpDutLCRa14Q6gttxyP"
        subject_id = adapter._subject_id(context=context, subject_token=token_multibase, species_code="100000108988")

        self.assertEqual(
            subject_id,
            f"did:web:acme.globaldatacare.es:animal:subject:{token_multibase}",
        )

    def test_subject_id_uses_person_kind(self) -> None:
        adapter = WakymaAdapter()
        context = AdapterContext(
            manufacturer="wakyma",
            tenant_id="acme",
            jurisdiction="es",
            sector="veterinary",
            issuer_did="did:web:acme.globaldatacare.es:employee:loader",
            audience_did="did:web:acme.globaldatacare.es",
            subject_did_prefix="did:web:acme.globaldatacare.es",
            subject_kind="person",
        )

        subject_id = adapter._subject_id(context=context, subject_token="123456", species_code="100000108988")

        self.assertTrue(subject_id.startswith("did:web:acme.globaldatacare.es:person:subject:"))

    def test_build_excluded_section_families_normalizes_valid_items(self) -> None:
        adapter = WakymaAdapter()

        excluded = adapter._build_excluded_section_families(
            {
                "excludedSectionFamilies": [
                    " Clínica:Vacunación ",
                    "clinica:*",
                    "*:medicamentos",
                    "invalid-without-colon",
                    "",
                ]
            }
        )

        self.assertEqual(
            excluded,
            {"clinica:vacunacion", "clinica:*", "*:medicamentos"},
        )

    def test_is_section_family_excluded_supports_exact_and_wildcards(self) -> None:
        adapter = WakymaAdapter()
        excluded = {"clinica:vacunacion", "clinica:*", "*:medicamentos"}

        self.assertTrue(
            adapter._is_section_family_excluded(
                section="Clínica",
                family="Vacunación",
                excluded_section_families=excluded,
            )
        )
        self.assertTrue(
            adapter._is_section_family_excluded(
                section="Clínica",
                family="Laboratorio",
                excluded_section_families=excluded,
            )
        )
        self.assertTrue(
            adapter._is_section_family_excluded(
                section="Otro",
                family="Medicamentos",
                excluded_section_families=excluded,
            )
        )
        self.assertFalse(
            adapter._is_section_family_excluded(
                section="Otro",
                family="Consultas",
                excluded_section_families=excluded,
            )
        )

    def test_read_records_excludes_configured_section_family(self) -> None:
        adapter = WakymaAdapter()
        context = AdapterContext(
            manufacturer="wakyma",
            tenant_id="acme",
            jurisdiction="es",
            sector="veterinary",
            issuer_did="did:web:acme.globaldatacare.es:employee:loader",
            audience_did="did:web:acme.globaldatacare.es",
            subject_did_prefix="did:web:acme.globaldatacare.es",
            strict_species_mapping=False,
            fhir_species_catalog={"100000108988": "Dogs"},
            species_local_to_fhir={
                "Perro": "100000108988",
                "PERRO": "100000108988",
                "perro": "100000108988",
            },
            schema_config={
                "fieldDefaults": {"section": "clinica"},
                "allowedSections": ["clinica"],
                "excludedSectionFamilies": ["clinica:vacunacion"],
            },
        )
        rows = [
            ParsedRow(
                row_number=2,
                values={
                    "Tipo": "Vacunación",
                    "Motivo": "Rabia",
                    "ID Interno Paciente": "123",
                    "Mascota": "Perro",
                    "Fecha": "2026-01-28",
                    "Hora": "13:30",
                },
            ),
            ParsedRow(
                row_number=3,
                values={
                    "Tipo": "Laboratorio",
                    "Motivo": "Hemograma",
                    "ID Interno Paciente": "456",
                    "Mascota": "Perro",
                    "Fecha": "2026-01-28",
                    "Hora": "14:00",
                },
            ),
        ]

        with NamedTemporaryFile(suffix=".xlsx") as tmp, patch(
            "adapter_ingestion.manufacturers.tabular_xlsx.read_xlsx_rows",
            return_value=rows,
        ):
            records = adapter.read_records(Path(tmp.name), context)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].family.lower(), "laboratorio")
        self.assertEqual(adapter.get_last_report().get("recordsDroppedSectionFamilyFilter"), 1)

    def test_resolves_public_owner_hash_only_for_public_organizations(self) -> None:
        adapter = WakymaAdapter()
        context = AdapterContext(
            manufacturer="wakyma",
            tenant_id="acme",
            jurisdiction="es",
            sector="veterinary",
            issuer_did="did:web:acme.globaldatacare.es:employee:loader",
            audience_did="did:web:acme.globaldatacare.es",
            subject_did_prefix="did:web:acme.globaldatacare.es",
            strict_species_mapping=False,
            fhir_species_catalog={"100000108988": "Dogs"},
            species_local_to_fhir={
                "Perro": "100000108988",
                "PERRO": "100000108988",
                "perro": "100000108988",
            },
            schema_config={
                "fieldMap": {
                    "owner": "Propietario",
                },
                "fieldDefaults": {"section": "clinica"},
                "ownerPublicRules": {
                    "enabled": True,
                    "containsAny": ["ayuntamiento"],
                    "excludeContainsAny": ["S.L.", "S.A."],
                    "publicIdPrefixes": ["P", "Q", "S"],
                    "identifierRegex": "^(?:[A-Z]\\d{7}[A-Z0-9]|\\d{8}[A-Z])$",
                    "relationship": "organization-owner",
                },
            },
        )
        rows = [
            ParsedRow(
                row_number=2,
                values={
                    "Tipo": "Consulta",
                    "Motivo": "Revisión",
                    "ID Interno Paciente": "123",
                    "Mascota": "Perro",
                    "Fecha": "2026-01-28",
                    "Hora": "13:30",
                    "Propietario": "Ayuntamiento de Sevilla P4109100A",
                },
            ),
            ParsedRow(
                row_number=3,
                values={
                    "Tipo": "Consulta",
                    "Motivo": "Revisión",
                    "ID Interno Paciente": "456",
                    "Mascota": "Perro",
                    "Fecha": "2026-01-28",
                    "Hora": "14:00",
                    "Propietario": "Veterinaria Centro S.L. B12345678",
                },
            ),
        ]

        with NamedTemporaryFile(suffix=".xlsx") as tmp, patch(
            "adapter_ingestion.manufacturers.tabular_xlsx.read_xlsx_rows",
            return_value=rows,
        ):
            records = adapter.read_records(Path(tmp.name), context)

        self.assertEqual(len(records), 2)
        self.assertTrue(records[0].owner_public_hash.startswith("z"))
        self.assertEqual(records[0].owner_public_name, "Ayuntamiento de Sevilla P4109100A")
        self.assertEqual(records[0].owner_public_relationship, "organization-owner")
        self.assertEqual(records[1].owner_public_hash, "")
        self.assertEqual(adapter.get_last_report().get("recordsWithPublicOwner"), 1)

    def test_read_records_accepts_csv_with_header_row_index(self) -> None:
        adapter = WakymaAdapter()
        context = AdapterContext(
            manufacturer="wakyma",
            tenant_id="acme",
            jurisdiction="es",
            sector="veterinary",
            issuer_did="did:web:acme.globaldatacare.es:employee:loader",
            audience_did="did:web:acme.globaldatacare.es",
            subject_did_prefix="did:web:acme.globaldatacare.es",
            strict_species_mapping=False,
            fhir_species_catalog={"100000108988": "Dogs"},
            species_local_to_fhir={
                "Perro": "100000108988",
                "PERRO": "100000108988",
                "perro": "100000108988",
            },
        )

        csv_content = "\n".join(
            [
                "Export Wakyma",
                "Tipo;Motivo;ID Interno Paciente;Mascota;Fecha;Hora",
                "Consulta;Revisión anual;123;Perro;28/01/2026;13:30",
            ]
        )

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
            tmp.write(csv_content)
            csv_path = Path(tmp.name)
        try:
            records = adapter.read_records(csv_path, context)
        finally:
            if csv_path.exists():
                csv_path.unlink()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].family, "Consulta")
        self.assertEqual(records[0].concept, "Revisión anual")
        self.assertEqual(records[0].species_fhir_code, "100000108988")
        self.assertTrue(records[0].subject_id.startswith("did:web:acme.globaldatacare.es:animal:subject:"))
        self.assertEqual(adapter.get_last_report().get("rowsRead"), 1)

    def test_read_records_uses_personal_id_when_subject_id_missing(self) -> None:
        adapter = WakymaAdapter()
        context = AdapterContext(
            manufacturer="wakyma",
            tenant_id="acme",
            jurisdiction="es",
            sector="veterinary",
            issuer_did="did:web:acme.globaldatacare.es:employee:loader",
            audience_did="did:web:acme.globaldatacare.es",
            subject_did_prefix="did:web:acme.globaldatacare.es",
            strict_species_mapping=False,
            fhir_species_catalog={"100000108988": "Dogs"},
            species_local_to_fhir={
                "Perro": "100000108988",
                "PERRO": "100000108988",
                "perro": "100000108988",
            },
            schema_config={
                "fieldMap": {
                    "subject_id": "Paciente",
                    "personal_id": "DNI",
                    "family": "Tipo",
                    "subfamily": "Tipo",
                    "concept": "Motivo",
                    "species": "Mascota",
                    "date": "Fecha",
                    "time": "Hora",
                },
                "fieldDefaults": {"section": "clinica"},
            },
            personal_id_resolver=lambda raw: (
                "11111111-1111-4111-8111-111111111111"
                if str(raw).strip() == "12345678A"
                else ""
            ),
        )
        rows = [
            ParsedRow(
                row_number=2,
                values={
                    "Tipo": "Consulta",
                    "Motivo": "Revisión",
                    "Paciente": "",
                    "DNI": "12345678A",
                    "Mascota": "Perro",
                    "Fecha": "2026-01-28",
                    "Hora": "13:30",
                },
            ),
        ]

        with NamedTemporaryFile(suffix=".xlsx") as tmp, patch(
            "adapter_ingestion.manufacturers.tabular_xlsx.read_xlsx_rows",
            return_value=rows,
        ):
            records = adapter.read_records(Path(tmp.name), context)

        self.assertEqual(len(records), 1)
        self.assertTrue(records[0].subject_id.startswith("did:web:acme.globaldatacare.es:animal:subject:"))

    def test_read_records_generates_anonymous_uuid_when_personal_id_empty(self) -> None:
        adapter = WakymaAdapter()
        context = AdapterContext(
            manufacturer="wakyma",
            tenant_id="acme",
            jurisdiction="es",
            sector="veterinary",
            issuer_did="did:web:acme.globaldatacare.es:employee:loader",
            audience_did="did:web:acme.globaldatacare.es",
            subject_did_prefix="did:web:acme.globaldatacare.es",
            strict_species_mapping=False,
            fhir_species_catalog={"100000108988": "Dogs"},
            species_local_to_fhir={
                "Perro": "100000108988",
                "PERRO": "100000108988",
                "perro": "100000108988",
            },
            schema_config={
                "fieldMap": {
                    "subject_id": "Paciente",
                    "personal_id": "DNI",
                    "family": "Tipo",
                    "subfamily": "Tipo",
                    "concept": "Motivo",
                    "species": "Mascota",
                    "date": "Fecha",
                    "time": "Hora",
                },
                "fieldDefaults": {"section": "clinica"},
            },
            personal_id_resolver=lambda raw: "",
        )
        rows = [
            ParsedRow(
                row_number=2,
                values={
                    "Tipo": "Consulta",
                    "Motivo": "Revisión",
                    "Paciente": "",
                    "DNI": "",
                    "Mascota": "Perro",
                    "Fecha": "2026-01-28",
                    "Hora": "13:30",
                },
            ),
        ]

        with NamedTemporaryFile(suffix=".xlsx") as tmp, patch(
            "adapter_ingestion.manufacturers.tabular_xlsx.read_xlsx_rows",
            return_value=rows,
        ):
            records = adapter.read_records(Path(tmp.name), context)

        self.assertEqual(len(records), 1)
        self.assertTrue(records[0].subject_id.startswith("did:web:acme.globaldatacare.es:animal:subject:"))

    def test_read_records_accepts_missing_loinc_with_generic_fallback(self) -> None:
        adapter = TabularXlsxAdapter()
        context = AdapterContext(
            manufacturer="tabular",
            tenant_id="acme",
            jurisdiction="es",
            sector="veterinary",
            issuer_did="did:web:acme.globaldatacare.es:employee:loader",
            audience_did="did:web:acme.globaldatacare.es",
            subject_did_prefix="did:web:acme.globaldatacare.es",
            strict_species_mapping=False,
            schema_config={
                "fieldMap": {
                    "section": "Seccion",
                    "family": "Familia",
                    "subfamily": "Subfamilia",
                    "concept": "Concepto",
                    "subject_id": "Paciente",
                }
            },
        )
        rows = [
            ParsedRow(
                row_number=2,
                values={
                    "Seccion": "Clinica",
                    "Familia": "Consultas",
                    "Subfamilia": "Revision",
                    "Concepto": "Consulta general",
                    "Paciente": "123",
                },
            ),
        ]

        with NamedTemporaryFile(suffix=".xlsx") as tmp, patch(
            "adapter_ingestion.manufacturers.tabular_xlsx.read_xlsx_rows",
            return_value=rows,
        ):
            records = adapter.read_records(Path(tmp.name), context)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].composition_section, "clinica:consultas")
        self.assertEqual(records[0].document_category_code, "")
        self.assertEqual(records[0].composition_type_code, "")
        self.assertEqual(adapter.get_last_report().get("recordsDroppedMissingLoincMapping"), 0)
        self.assertEqual(
            adapter.get_last_report().get("missingLoincBySectionFamily"),
            {"clinica:consultas": 1},
        )

    def test_read_records_defaults_missing_section_and_family(self) -> None:
        adapter = TabularXlsxAdapter()
        context = AdapterContext(
            manufacturer="tabular",
            tenant_id="acme",
            jurisdiction="es",
            sector="veterinary",
            issuer_did="did:web:acme.globaldatacare.es:employee:loader",
            audience_did="did:web:acme.globaldatacare.es",
            subject_did_prefix="did:web:acme.globaldatacare.es",
            strict_species_mapping=False,
            schema_config={
                "fieldMap": {
                    "concept": "Concepto",
                    "subject_id": "Paciente",
                }
            },
        )
        rows = [
            ParsedRow(
                row_number=2,
                values={
                    "Concepto": "Observacion libre",
                    "Paciente": "123",
                },
            ),
        ]

        with NamedTemporaryFile(suffix=".xlsx") as tmp, patch(
            "adapter_ingestion.manufacturers.tabular_xlsx.read_xlsx_rows",
            return_value=rows,
        ):
            records = adapter.read_records(Path(tmp.name), context)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].section, "default")
        self.assertEqual(records[0].family, "default")
        self.assertEqual(records[0].subfamily, "default")
        self.assertEqual(records[0].composition_section, "default")

    def test_read_records_sanitizes_non_concept_fields_and_birthyear(self) -> None:
        adapter = TabularXlsxAdapter()
        context = AdapterContext(
            manufacturer="tabular",
            tenant_id="acme",
            jurisdiction="es",
            sector="veterinary",
            issuer_did="did:web:acme.globaldatacare.es:employee:loader",
            audience_did="did:web:acme.globaldatacare.es",
            subject_did_prefix="did:web:acme.globaldatacare.es",
            strict_species_mapping=False,
            schema_config={
                "fieldMap": {
                    "subject_id": "IdMascota",
                    "concept": "Concepto",
                    "species": "Especie",
                    "breed": "Raza",
                    "genderStatus": "Esterilizado",
                    "birthyear": "Nacimiento",
                }
            },
        )
        rows = [
            ParsedRow(
                row_number=2,
                values={
                    "IdMascota": "['3345A']",
                    "Concepto": "['texto largo con [ ] y comillas']",
                    "Especie": "['dog']",
                    "Raza": "['westie', 'grifon-de-bruselas']",
                    "Esterilizado": "['True']",
                    "Nacimiento": "2015-07-17 11:49:00.000",
                },
            ),
        ]

        with NamedTemporaryFile(suffix=".xlsx") as tmp, patch(
            "adapter_ingestion.manufacturers.tabular_xlsx.read_xlsx_rows",
            return_value=rows,
        ):
            records = adapter.read_records(Path(tmp.name), context)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].species_local, "dog")
        self.assertEqual(records[0].animal_breed_code, "westie, grifon-de-bruselas")
        self.assertEqual(records[0].animal_gender_status_code, "neutered")
        self.assertEqual(records[0].subject_birthyear, "2015")
        self.assertEqual(records[0].concept, "['texto largo con [ ] y comillas']")


if __name__ == "__main__":
    unittest.main()
