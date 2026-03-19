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
from adapter_ingestion.models import AdapterContext, CanonicalRecord
from adapter_ingestion.pipeline import run_pipeline


class PipelineTests(unittest.TestCase):
    @staticmethod
    def _patient_entries(result: object) -> list[dict]:
        return [
            entry
            for entry in result.composition_message["body"]["data"]
            if isinstance(entry, dict)
            and isinstance(entry.get("resource"), dict)
            and entry["resource"].get("resourceType") == "Patient"
        ]

    @staticmethod
    def _contained_by_type(patient_resource: dict, resource_type: str) -> list[dict]:
        contained = patient_resource.get("contained", [])
        return [item for item in contained if isinstance(item, dict) and item.get("resourceType") == resource_type]

    @staticmethod
    def _patient_for_subject(result: object, subject_id: str) -> dict:
        for entry in PipelineTests._patient_entries(result):
            resource = entry["resource"]
            claims = resource.get("meta", {}).get("claims", {})
            if claims.get("Patient.identifier") == subject_id:
                return resource
        raise AssertionError(f"Patient entry not found for subject '{subject_id}'")

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
        self.assertEqual(result.summary["patientEntries"], 2)

        patient_entries = self._patient_entries(result)
        self.assertEqual(len(patient_entries), 2)

        patient_subject_1 = self._patient_for_subject(result, "urn:gdc:acme:patient:subject:001")
        contained_subject_1 = patient_subject_1["contained"]

        docrefs_subject_1 = self._contained_by_type(patient_subject_1, "DocumentReference")
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

        compositions_subject_1 = self._contained_by_type(patient_subject_1, "Composition")
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

        encounter_subject_1 = self._contained_by_type(patient_subject_1, "Encounter")
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
        patient = self._patient_entries(result)[0]["resource"]
        docref = self._contained_by_type(patient, "DocumentReference")[0]
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
        patient = self._patient_entries(result)[0]["resource"]
        docref = self._contained_by_type(patient, "DocumentReference")[0]
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
        self.assertEqual(result.summary["patientEntries"], 1)

        patient = self._patient_entries(result)[0]["resource"]
        patient_claims = patient["meta"]["claims"]
        patient_link_values = patient_claims["Patient.link"].split(",")
        self.assertEqual(len(patient_link_values), 1)
        self.assertEqual(
            patient_link_values[0],
            "urn:cds:ES:v1:organization:multibase:zownerhash001",
        )

        compositions = self._contained_by_type(patient, "Composition")
        self.assertEqual(len(compositions), 1)
        composition = compositions[0]
        claims = composition["meta"]["claims"]
        self.assertNotIn("Composition.relatedPerson", claims)
        self.assertNotIn("Composition.relatedPerson.identifier", claims)

        contained = patient["contained"]
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
                animal_breed_code="http://snomed.info/sct|58108001",
                animal_gender_status_code="http://hl7.org/fhir/animal-genderstatus|neutered",
                owner_public_hash="zownerhash001",
                owner_public_name="Ayuntamiento de Sevilla",
                owner_public_relationship="organization-owner",
            ),
        ]

        result = run_pipeline(records=records, context=context, coding_assistant=NoopCodingAssistant())
        self.assertEqual(result.summary["patientEntries"], 1)

        patient = self._patient_entries(result)[0]["resource"]
        patient_claims = patient["meta"]["claims"]
        self.assertEqual(
            patient_claims["Patient.identifier"],
            "did:web:acme.example.com:animal:subject:zabc",
        )
        self.assertEqual(
            patient_claims["Patient.link"],
            "urn:cds:ES:v1:organization:multibase:zownerhash001",
        )
        self.assertNotIn("Patient.link.display", patient_claims)
        self.assertEqual(patient_claims["Patient.animal-species"], "http://hl7.org/fhir/target-species|100000108988")
        self.assertEqual(patient_claims["Patient.animal-breed"], "http://snomed.info/sct|58108001")
        self.assertEqual(
            patient_claims["Patient.animal-genderstatus"],
            "http://hl7.org/fhir/animal-genderstatus|neutered",
        )
        self.assertNotIn("Patient.contact.organization.identifier", patient_claims)

        compositions = self._contained_by_type(patient, "Composition")
        self.assertEqual(len(compositions), 1)
        entries = compositions[0]["meta"]["claims"]["Composition.entry"].split(",")
        self.assertEqual(len(entries), 2)
        self.assertTrue(all(item.startswith("urn:uuid:") for item in entries))

        related_persons = self._contained_by_type(patient, "RelatedPerson")
        self.assertEqual(len(related_persons), 1)
        self.assertEqual(
            related_persons[0]["meta"]["claims"]["RelatedPerson.identifier"],
            patient_claims["Patient.link"],
        )

if __name__ == "__main__":
    unittest.main()
