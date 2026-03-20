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

from adapter_ingestion.ai.base import NoopCodingAssistant
from adapter_ingestion.manufacturers.registry import get_adapter
from adapter_ingestion.models import AdapterContext, CanonicalRecord
from adapter_ingestion.pipeline import _claims_have_meaningful_values, run_pipeline
from adapter_ingestion.service.api_config import extract_embedded_api_config


class PipelineTests(unittest.TestCase):
    APPMYPETS_EXAMPLE = ROOT.parent / "examples" / "AppMyPets-api-config.xlsx"

    @staticmethod
    def _subject_entries(result: object) -> list[dict]:
        return [
            entry
            for entry in result.composition_message["body"]["data"]
            if isinstance(entry, dict)
            and isinstance(entry.get("resource"), dict)
            and entry["resource"].get("resourceType") == "Subject"
        ]

    @staticmethod
    def _contained_by_type(subject_resource: dict, resource_type: str) -> list[dict]:
        contained = subject_resource.get("contained", [])
        return [item for item in contained if isinstance(item, dict) and item.get("resourceType") == resource_type]

    @staticmethod
    def _subject_for_subject_id(result: object, subject_id: str) -> dict:
        for entry in PipelineTests._subject_entries(result):
            resource = entry["resource"]
            claims = resource.get("meta", {}).get("claims", {})
            if claims.get("Subject.id") == subject_id:
                return resource
        raise AssertionError(f"Subject entry not found for subject '{subject_id}'")

    def test_does_not_include_animal_claims_for_person_subject_kind(self) -> None:
        context = AdapterContext(
            manufacturer="qvet",
            tenant_id="acme",
            jurisdiction="es",
            sector="health-care",
            issuer_did="did:web:acme.example.com:employee:loader",
            audience_did="did:web:acme.example.com",
            subject_kind="person",
            data_use="individual",
        )
        record = CanonicalRecord(
            source_row_number=2,
            source_id="a1",
            timestamp="2026-01-01T10:00:00Z",
            subject_id="urn:gdc:acme:patient:subject:001",
            section="clinica",
            family="vacunas",
            subfamily="VACUNA", 
            concept="Consulta", 
            composition_section="immunizations",
            document_type_code="urn:gdc:qvet:clinica:vacunas:vacuna-perro",
            attributes={"SECCION": "clinica", "FAMILIA": "vacunas"},
            species_local="Perro",
            species_fhir_code="100000108988",
            subject_birthyear="2020",
            subject_birthsex="M",
            animal_breed_code="westie",
            animal_gender_status_code="intact",
        )
        result = run_pipeline(records=[record], context=context, coding_assistant=NoopCodingAssistant())
        subject = self._subject_entries(result)[0]["resource"]
        claims = subject["meta"]["claims"]
        self.assertIn("Subject.id", claims)
        self.assertNotIn("Subject.animal-species", claims)
        self.assertNotIn("Subject.animal-breed", claims)
        self.assertNotIn("Subject.animal-genderstatus", claims)

    def test_groups_compositions_by_subject_and_section(self) -> None:
        context = AdapterContext(
            manufacturer="qvet",
            tenant_id="acme",
            jurisdiction="es",
            sector="health-care",
            issuer_did="did:web:acme.example.com:employee:loader",
            audience_did="did:web:gateway.example.com:host",
            data_use="individual",
        )

        records = [
            CanonicalRecord(
                source_row_number=2,
                source_id="a1",
                timestamp="2026-01-01T10:00:00Z",
                subject_id="urn:gdc:acme:patient:subject:001",
                section="clinica",
                family="vacunas",
                subfamily="VACUNA PERRO",
                concept="Vacuna anual",
                composition_section="immunizations",
                document_type_code="urn:gdc:qvet:clinica:vacunas:vacuna-perro",
                attributes={"SECCION": "clinica", "FAMILIA": "vacunas", "SUBFAMILIA": "VACUNA PERRO"},
            ),
            CanonicalRecord(
                source_row_number=3,
                source_id="a2",
                timestamp="2026-01-01T11:00:00Z",
                subject_id="urn:gdc:acme:patient:subject:001",
                section="clinica",
                family="laboratorio",
                subfamily="TEST RAPIDOS",
                concept="Test rápido",
                composition_section="laboratory",
                document_type_code="urn:gdc:qvet:clinica:laboratorio:test-rapidos",
                attributes={"SECCION": "clinica", "FAMILIA": "laboratorio", "SUBFAMILIA": "TEST RAPIDOS"},
            ),
            CanonicalRecord(
                source_row_number=4,
                source_id="b1",
                timestamp="2026-01-02T10:00:00Z",
                subject_id="urn:gdc:acme:patient:subject:002",
                section="clinica",
                family="vacunas",
                subfamily="VACUNA GATO",
                concept="Vacuna felina",
                composition_section="immunizations",
                document_type_code="urn:gdc:qvet:clinica:vacunas:vacuna-gato",
                attributes={"SECCION": "clinica", "FAMILIA": "vacunas", "SUBFAMILIA": "VACUNA GATO"},
            ),
            CanonicalRecord(
                source_row_number=5,
                source_id="a3",
                timestamp="2026-01-03T10:00:00Z",
                subject_id="urn:gdc:acme:patient:subject:001",
                section="clinica",
                family="vacunas",
                subfamily="VACUNA GATO",
                concept="Refuerzo vacunal",
                composition_section="immunizations",
                document_type_code="urn:gdc:qvet:clinica:vacunas:vacuna-gato",
                attributes={"SECCION": "clinica", "FAMILIA": "vacunas", "SUBFAMILIA": "VACUNA GATO"},
            ),
        ]

        result = run_pipeline(records=records, context=context, coding_assistant=NoopCodingAssistant())

        self.assertEqual(result.summary["recordsTotal"], 4)
        self.assertEqual(result.summary["subjectsTotal"], 2)
        self.assertEqual(result.summary["documentReferenceEntries"], 4)
        self.assertEqual(result.summary["encounterEntries"], 4)
        self.assertEqual(result.summary["compositionEntries"], 3)
        self.assertEqual(result.summary["subjectEntries"], 2)

        subject_entries = self._subject_entries(result)
        self.assertEqual(len(subject_entries), 2)

        subject_1 = self._subject_for_subject_id(result, "urn:gdc:acme:patient:subject:001")
        contained_subject_1 = subject_1["contained"]

        docrefs_subject_1 = self._contained_by_type(subject_1, "DocumentReference")
        self.assertEqual(len(docrefs_subject_1), 3)
        first_claims = docrefs_subject_1[0]["meta"]["claims"]
        self.assertIn("DocumentReference.text", first_claims)
        self.assertIn("<table>", first_claims["DocumentReference.text"])
        self.assertEqual(first_claims["DocumentReference.author"], "")
        self.assertIn("http://loinc.org|", first_claims["DocumentReference.category"])
        self.assertNotIn("DocumentReference.context", first_claims)
        self.assertNotIn("DocumentReference.contenttype", first_claims)
        self.assertNotIn("DocumentReference.contentdata", first_claims)
        self.assertRegex(first_claims["DocumentReference.identifier"], r"^[0-9a-fA-F-]{36}$")

        compositions_subject_1 = self._contained_by_type(subject_1, "Composition")
        self.assertEqual(len(compositions_subject_1), 2)
        first_comp_claims = compositions_subject_1[0]["meta"]["claims"]
        self.assertEqual(first_comp_claims["Composition.author"], "")
        self.assertRegex(first_comp_claims["Composition.identifier"], r"^[0-9a-fA-F-]{36}$")

        comp_for_subject1_imm = [
            resource
            for resource in compositions_subject_1
            if resource["meta"]["claims"]["Composition.subject"] == "urn:gdc:acme:patient:subject:001"
            and resource["meta"]["claims"]["Composition.section"] == "http://loinc.org|11369-6"
        ]
        self.assertEqual(len(comp_for_subject1_imm), 1)
        target_comp = comp_for_subject1_imm[0]
        target_claims = target_comp["meta"]["claims"]
        self.assertEqual(target_claims["Composition.type"], "http://loinc.org|11369-6")
        entry_refs = target_claims["Composition.entry"].split(",")
        self.assertEqual(len(entry_refs), 4)
        self.assertTrue(all(item.startswith("urn:uuid:") for item in entry_refs))

        contained_ids = {contained["id"] for contained in contained_subject_1}
        self.assertTrue({item.replace("urn:uuid:", "") for item in entry_refs}.issubset(contained_ids))

        encounter_subject_1 = self._contained_by_type(subject_1, "Encounter")
        self.assertEqual(len(encounter_subject_1), 3)
        self.assertTrue(
            all(
                "Encounter.class" in encounter["meta"]["claims"]
                and encounter["meta"]["claims"]["Encounter.class"].endswith("|AMB")
                for encounter in encounter_subject_1
            )
        )

        all_subject_1_docrefs = [
            contained
            for contained in contained_subject_1
            if contained.get("resourceType") == "DocumentReference"
        ]
        self.assertTrue(all("DocumentReference.subject" in contained["meta"]["claims"] for contained in all_subject_1_docrefs))
        self.assertNotIn("Composition.relatedPerson", target_claims)

    def test_does_not_map_xhtml_to_attachment_claims_even_when_flag_enabled(self) -> None:
        context = AdapterContext(
            manufacturer="qvet",
            tenant_id="acme",
            jurisdiction="es",
            sector="health-care",
            issuer_did="did:web:acme.example.com:employee:loader",
            audience_did="did:web:gateway.example.com:host",
            embed_xhtml_content=True,
            data_use="individual",
        )
        record = CanonicalRecord(
            source_row_number=2,
            source_id="a1",
            timestamp="2026-01-01T10:00:00Z",
            subject_id="urn:gdc:acme:patient:subject:001",
            section="clinica",
            family="vacunas",
            subfamily="VACUNA PERRO",
            concept="Vacuna anual",
            composition_section="immunizations",
            document_type_code="urn:gdc:qvet:clinica:vacunas:vacuna-perro",
            attributes={"SECCION": "clinica", "FAMILIA": "vacunas"},
        )

        result = run_pipeline(records=[record], context=context, coding_assistant=NoopCodingAssistant())
        subject = self._subject_entries(result)[0]["resource"]
        docref = self._contained_by_type(subject, "DocumentReference")[0]
        claims = docref["meta"]["claims"]
        self.assertIn("DocumentReference.text", claims)
        self.assertNotIn("DocumentReference.contenttype", claims)
        self.assertNotIn("DocumentReference.contentdata", claims)

    def test_omits_document_text_for_secondary_use(self) -> None:
        context = AdapterContext(
            manufacturer="qvet",
            tenant_id="acme",
            jurisdiction="es",
            sector="research",
            issuer_did="did:web:acme.example.com:employee:loader",
            audience_did="did:web:gateway.example.com:host",
            data_use="secondary",
        )
        record = CanonicalRecord(
            source_row_number=2,
            source_id="a1",
            timestamp="2026-01-01T10:00:00Z",
            subject_id="urn:gdc:acme:patient:subject:001",
            section="clinica",
            family="vacunas",
            subfamily="VACUNA PERRO",
            concept="Vacuna anual",
            composition_section="immunizations",
            document_type_code="urn:gdc:qvet:clinica:vacunas:vacuna-perro",
            attributes={"SECCION": "clinica", "FAMILIA": "vacunas"},
        )
        result = run_pipeline(records=[record], context=context, coding_assistant=NoopCodingAssistant())
        subject = self._subject_entries(result)[0]["resource"]
        docref = self._contained_by_type(subject, "DocumentReference")[0]
        claims = docref["meta"]["claims"]
        self.assertNotIn("DocumentReference.text", claims)

    def test_adds_operation_outcome_entries_for_row_issues(self) -> None:
        context = AdapterContext(
            manufacturer="qvet",
            tenant_id="acme",
            jurisdiction="es",
            sector="health-care",
            issuer_did="did:web:acme.example.com:employee:loader",
            audience_did="did:web:gateway.example.com:host",
            data_use="individual",
        )
        record = CanonicalRecord(
            source_row_number=2,
            source_id="a1",
            timestamp="2026-01-01T10:00:00Z",
            subject_id="urn:gdc:acme:patient:subject:001",
            section="clinica",
            family="vacunas",
            subfamily="VACUNA PERRO",
            concept="Vacuna anual",
            composition_section="immunizations",
            document_type_code="urn:gdc:qvet:clinica:vacunas:vacuna-perro",
            attributes={"SECCION": "clinica", "FAMILIA": "vacunas"},
        )
        row_issues = [
            {
                "rowNumber": 10,
                "code": "missing-loinc-mapping",
                "sectionFamily": "clinica:laboratorio",
                "diagnostics": "Missing required LOINC mapping for section:family 'clinica:laboratorio'.",
            }
        ]

        result = run_pipeline(
            records=[record],
            context=context,
            coding_assistant=NoopCodingAssistant(),
            row_issues=row_issues,
        )

        self.assertEqual(result.summary["compositionEntries"], 1)
        self.assertEqual(result.summary["operationOutcomeEntries"], 1)
        entries = result.composition_message["body"]["data"]
        oo_entries = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and isinstance(entry.get("resource"), dict)
            and entry["resource"].get("resourceType") == "OperationOutcome"
        ]
        self.assertEqual(len(oo_entries), 1)
        oo_resource = oo_entries[0]["resource"]
        self.assertEqual(oo_resource["issue"][0]["severity"], "warning")
        self.assertIn("Missing required LOINC mapping", oo_resource["issue"][0]["diagnostics"])
        self.assertIn("response", oo_entries[0])
        self.assertEqual(oo_entries[0]["response"]["status"], "422")
        self.assertEqual(oo_entries[0]["response"]["outcome"]["resourceType"], "OperationOutcome")

    def test_adds_related_person_for_public_owner_hash(self) -> None:
        context = AdapterContext(
            manufacturer="qvet",
            tenant_id="acme",
            jurisdiction="es",
            sector="health-care",
            issuer_did="did:web:acme.example.com:employee:loader",
            audience_did="did:web:gateway.example.com:host",
            data_use="individual",
        )
        records = [
            CanonicalRecord(
                source_row_number=2,
                source_id="a1",
                timestamp="2026-01-01T10:00:00Z",
                subject_id="did:web:acme.example.com:animal:subject:zabc",
                section="clinica",
                family="laboratorio",
                subfamily="TEST RAPIDOS",
                concept="Hemograma",
                composition_section="clinica:laboratorio",
                document_type_code="urn:gdc:qvet:clinica:laboratorio:test-rapidos",
                attributes={"SECCION": "clinica", "FAMILIA": "laboratorio"},
                owner_public_hash="zownerhash001",
                owner_public_name="Ayuntamiento de Sevilla",
                owner_public_relationship="organization-owner",
            ),
            CanonicalRecord(
                source_row_number=3,
                source_id="a2",
                timestamp="2026-01-01T11:00:00Z",
                subject_id="did:web:acme.example.com:animal:subject:zabc",
                section="clinica",
                family="laboratorio",
                subfamily="TEST RAPIDOS",
                concept="Bioquimica",
                composition_section="clinica:laboratorio",
                document_type_code="urn:gdc:qvet:clinica:laboratorio:test-rapidos",
                attributes={"SECCION": "clinica", "FAMILIA": "laboratorio"},
                owner_public_hash="zownerhash001",
                owner_public_name="Ayuntamiento de Sevilla",
                owner_public_relationship="organization-owner",
            ),
        ]

        result = run_pipeline(records=records, context=context, coding_assistant=NoopCodingAssistant())
        self.assertEqual(result.summary["relatedPersonEntries"], 1)
        self.assertEqual(result.summary["subjectEntries"], 1)

        subject = self._subject_entries(result)[0]["resource"]
        subject_claims = subject["meta"]["claims"]
        subject_link_values = subject_claims["Subject.link"].split(",")
        self.assertEqual(len(subject_link_values), 1)
        self.assertEqual(
            subject_link_values[0],
            "urn:cds:ES:v1:organization:multibase:zownerhash001",
        )

        compositions = self._contained_by_type(subject, "Composition")
        self.assertEqual(len(compositions), 1)
        composition = compositions[0]
        claims = composition["meta"]["claims"]
        self.assertNotIn("Composition.relatedPerson", claims)
        self.assertNotIn("Composition.relatedPerson.identifier", claims)

        contained = subject["contained"]
        related_persons = [item for item in contained if item.get("resourceType") == "RelatedPerson"]
        self.assertEqual(len(related_persons), 1)
        rp_claims = related_persons[0]["meta"]["claims"]
        self.assertEqual(
            rp_claims["RelatedPerson.identifier"],
            "urn:cds:ES:v1:organization:multibase:zownerhash001",
        )
        self.assertNotIn("RelatedPerson.identifier.value", rp_claims)
        self.assertEqual(
            rp_claims["RelatedPerson.patient"],
            "did:web:acme.example.com:animal:subject:zabc",
        )

    def test_adds_patient_when_owner_public_and_patient_rule_enabled(self) -> None:
        context = AdapterContext(
            manufacturer="qvet",
            tenant_id="acme",
            jurisdiction="es",
            sector="health-care",
            issuer_did="did:web:acme.example.com:employee:loader",
            audience_did="did:web:gateway.example.com:host",
            language="es-ES",
            fhir_species_system="http://hl7.org/fhir/target-species",
            fhir_species_catalog={"100000108988": "Dogs"},
            data_use="individual",
        )
        records = [
            CanonicalRecord(
                source_row_number=2,
                source_id="a1",
                timestamp="2026-01-01T10:00:00Z",
                subject_id="did:web:acme.example.com:animal:subject:zabc",
                section="clinica",
                family="laboratorio",
                subfamily="TEST RAPIDOS",
                concept="Hemograma",
                composition_section="clinica:laboratorio",
                document_type_code="urn:gdc:qvet:clinica:laboratorio:test-rapidos",
                attributes={"SECCION": "clinica", "FAMILIA": "laboratorio"},
                species_local="Canina",
                species_fhir_code="100000108988",
                subject_birthyear="2015",
                subject_birthsex="male",
                animal_breed_code="http://snomed.info/sct|58108001",
                animal_gender_status_code="http://hl7.org/fhir/animal-genderstatus|neutered",
                owner_public_hash="zownerhash001",
                owner_public_name="Ayuntamiento de Sevilla",
                owner_public_relationship="organization-owner",
            ),
        ]

        result = run_pipeline(records=records, context=context, coding_assistant=NoopCodingAssistant())
        self.assertEqual(result.summary["subjectEntries"], 1)

        subject = self._subject_entries(result)[0]["resource"]
        subject_claims = subject["meta"]["claims"]
        self.assertEqual(
            subject_claims["Subject.id"],
            "did:web:acme.example.com:animal:subject:zabc",
        )
        self.assertEqual(
            subject_claims["Subject.link"],
            "urn:cds:ES:v1:organization:multibase:zownerhash001",
        )
        self.assertNotIn("Subject.link.display", subject_claims)
        self.assertEqual(subject_claims["Subject.birthyear"], "2015")
        self.assertEqual(subject_claims["Subject.birthsex"], "male")
        self.assertEqual(subject_claims["Subject.animal-species"], "http://hl7.org/fhir/target-species|100000108988")
        self.assertEqual(subject_claims["Subject.animal-breed"], "http://snomed.info/sct|58108001")
        self.assertEqual(
            subject_claims["Subject.animal-genderstatus"],
            "http://hl7.org/fhir/animal-genderstatus|neutered",
        )
        self.assertNotIn("Subject.contact.organization.identifier", subject_claims)

        compositions = self._contained_by_type(subject, "Composition")
        self.assertEqual(len(compositions), 1)
        entries = compositions[0]["meta"]["claims"]["Composition.entry"].split(",")
        self.assertEqual(len(entries), 2)
        self.assertTrue(all(item.startswith("urn:uuid:") for item in entries))

        related_persons = self._contained_by_type(subject, "RelatedPerson")
        self.assertEqual(len(related_persons), 1)
        self.assertEqual(
            related_persons[0]["meta"]["claims"]["RelatedPerson.identifier"],
            subject_claims["Subject.link"],
        )

    @unittest.skipUnless(APPMYPETS_EXAMPLE.exists(), "Local AppMyPets example not available")
    def test_appmypets_example_marks_empty_optional_resources_as_discardable(self) -> None:
        extracted = extract_embedded_api_config(self.APPMYPETS_EXAMPLE)
        self.assertIsNotNone(extracted)

        adapter = get_adapter("api-config")
        context = AdapterContext(
            manufacturer="api-config",
            tenant_id="acme",
            jurisdiction="es",
            sector="onehealth-research",
            issuer_did="did:web:acme.example.com:employee:loader",
            audience_did="did:web:acme.example.com",
            language=extracted.get("runtimeDefaults", {}).get("language", "es"),
            subject_did_prefix="did:web:acme.example.com",
            strict_species_mapping=False,
            schema_config=extracted["schemaConfig"],
        )

        records = adapter.read_records(self.APPMYPETS_EXAMPLE, context)
        self.assertGreater(len(records), 0)

        first_record = records[0]
        self.assertEqual(first_record.attributes.get("weight"), "SIN DATO")
        self.assertEqual(first_record.attributes.get("petidvaccinestatus"), "SIN DATO")
        self.assertEqual(first_record.attributes.get("vaccineexpirationdate"), "SIN DATO")
        self.assertEqual(first_record.attributes.get("insurancecompany"), "SIN DATO")
        self.assertEqual(first_record.attributes.get("insuranceexpirationdate"), "SIN DATO")

        observation_claims = {
            "Observation.identifier": "urn:uuid:test-observation",
            "Observation.subject": first_record.subject_id,
            "Observation.code": "http://loinc.org|29463-7",
            "Observation.value": first_record.attributes.get("weight", ""),
        }
        self.assertFalse(
            _claims_have_meaningful_values(
                observation_claims,
                ignored_claim_keys={
                    "Observation.identifier",
                    "Observation.subject",
                    "Observation.code",
                },
            )
        )

        procedure_claims = {
            "Procedure.identifier": "urn:uuid:test-procedure",
            "Procedure.subject": first_record.subject_id,
            "Procedure.code-display": first_record.attributes.get("petidvaccinestatus", ""),
            "Procedure.performed": first_record.attributes.get("vaccineexpirationdate", ""),
        }
        self.assertFalse(
            _claims_have_meaningful_values(
                procedure_claims,
                ignored_claim_keys={
                    "Procedure.identifier",
                    "Procedure.subject",
                },
            )
        )

        coverage_claims = {
            "Coverage.identifier": "urn:uuid:test-coverage",
            "Coverage.beneficiary": first_record.subject_id,
            "Coverage.insurer": first_record.attributes.get("insurancecompany", ""),
            "Coverage.period.end": first_record.attributes.get("insuranceexpirationdate", ""),
        }
        self.assertFalse(
            _claims_have_meaningful_values(
                coverage_claims,
                ignored_claim_keys={
                    "Coverage.identifier",
                    "Coverage.beneficiary",
                },
            )
        )

    @unittest.skipUnless(APPMYPETS_EXAMPLE.exists(), "Local AppMyPets example not available")
    def test_appmypets_customer_master_does_not_create_encounters_without_service_signals(self) -> None:
        extracted = extract_embedded_api_config(self.APPMYPETS_EXAMPLE)
        self.assertIsNotNone(extracted)

        adapter = get_adapter("api-config")
        context = AdapterContext(
            manufacturer="api-config",
            tenant_id="acme",
            jurisdiction="es",
            sector="onehealth-research",
            issuer_did="did:web:acme.example.com:employee:loader",
            audience_did="did:web:acme.example.com",
            language=extracted.get("runtimeDefaults", {}).get("language", "es"),
            subject_did_prefix="did:web:acme.example.com",
            strict_species_mapping=False,
            schema_config=extracted["schemaConfig"],
        )

        records = adapter.read_records(self.APPMYPETS_EXAMPLE, context)
        self.assertGreater(len(records), 0)
        self.assertTrue(all(str(record.section or "").strip().lower() == "default" for record in records))
        self.assertTrue(all(str(record.family or "").strip().lower() == "default" for record in records))

        result = run_pipeline(records=records, context=context, coding_assistant=NoopCodingAssistant())

        self.assertEqual(result.summary["recordsTotal"], 500)
        self.assertEqual(result.summary["encounterEntries"], 0)
        self.assertEqual(result.summary["documentReferenceEntries"], 500)
        self.assertEqual(result.summary["subjectEntries"], 500)
        self.assertEqual(result.summary["patientEntries"], 500)
        self.assertEqual(result.summary["compositionEntries"], 500)

        subject = self._subject_entries(result)[0]["resource"]
        self.assertEqual(self._contained_by_type(subject, "Encounter"), [])

if __name__ == "__main__":
    unittest.main()
