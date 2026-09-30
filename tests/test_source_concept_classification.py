# Flow contract: classify heterogeneous source concepts without using sheet names, inventing codes, species or sex.
# 1. Hierarchy and free text may yield multiple review candidates from one row.
# 2. Clinical candidates remain non-authoritative until reviewed.
# 3. Retail-only concepts remain ChargeItem candidates and missing demographics stay absent.

from adapter_ingestion.source_concept_classification import classify_source_concept


def test_vaccine_and_sedation_hierarchies_yield_clinical_review_candidates() -> None:
    vaccine = classify_source_concept(
        section="Servicios Clínica",
        family="Servicios veterinarios",
        subfamily="Vacunas",
        concept="Vacuna rabia + aplicación",
        subject_kind="animal",
    )
    sedation = classify_source_concept(
        section="CLINICA",
        family="TRATAMIENTOS",
        subfamily="SEDACIÓN",
        concept="Sedación para radiografía",
        subject_kind="animal",
    )

    assert [item.resource_type for item in vaccine] == ["Immunization"]
    assert vaccine[0].source_text == "Vacuna rabia + aplicación"
    assert [item.resource_type for item in sedation] == ["Procedure"]


def test_multiline_treatment_keeps_lines_and_multiple_possible_resource_types() -> None:
    candidates = classify_source_concept(
        section="CLINICA",
        family="CONSULTA",
        subfamily="OFTALMOLOGÍA",
        concept="Control ocular",
        treatment="trusopt 1 gota 2 veces al día\npreforte 1 gota 3 veces al dia",
        subject_kind="animal",
    )

    assert [(item.resource_type, item.source_text) for item in candidates] == [
        ("MedicationStatement", "trusopt 1 gota 2 veces al día"),
        ("MedicationStatement", "preforte 1 gota 3 veces al dia"),
    ]


def test_retail_product_is_not_promoted_to_a_clinical_event() -> None:
    candidates = classify_source_concept(
        section="TIENDA",
        family="HIGIENE",
        subfamily="TOALLITAS",
        concept="Toallitas húmedas 40 unidades",
        subject_kind="animal",
    )

    assert [item.resource_type for item in candidates] == ["ChargeItem"]
    assert all(item.subject_species == "" and item.subject_sex == "" for item in candidates)


def test_unclassified_concept_stays_explicitly_pending() -> None:
    candidates = classify_source_concept(
        section="",
        family="",
        subfamily="",
        concept="concepto interno 47",
        subject_kind="person",
    )

    assert [item.resource_type for item in candidates] == ["Unclassified"]
    assert candidates[0].confidence == "pending"


def test_fracture_concept_is_a_condition_candidate_not_a_diagnostic_report() -> None:
    candidates = classify_source_concept(
        section="CLINICA",
        family="DIAGNOSTICO",
        subfamily="TRAUMATOLOGIA",
        concept="Fractura de sesamoideo",
        subject_kind="animal",
    )

    assert [item.resource_type for item in candidates] == ["Condition"]
    assert candidates[0].source_text == "Fractura de sesamoideo"


def test_vaccination_uncertainty_or_future_intent_is_not_a_completed_immunization_candidate() -> None:
    uncertain = classify_source_concept(
        section="CLINICA",
        family="NORMAL",
        subfamily="NORMAL",
        concept="No saben si está vacunado; enviamos muestra al laboratorio",
        subject_kind="animal",
    )
    future = classify_source_concept(
        section="CLINICA",
        family="NORMAL",
        subfamily="NORMAL",
        concept="Repetiremos la analítica en abril si le quieren vacunar",
        subject_kind="animal",
    )

    assert all(item.resource_type != "Immunization" for item in uncertain)
    assert all(item.resource_type != "Immunization" for item in future)


def test_allergy_wording_targets_allergy_intolerance_before_medication() -> None:
    candidates = classify_source_concept(
        section="CLINICA",
        family="ALERGIAS",
        subfamily="MEDICAMENTOS",
        concept="Alergia a penicilina",
        subject_kind="animal",
    )

    assert [item.resource_type for item in candidates] == ["AllergyIntolerance"]
