# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.
# Qvet clinical context yields proposal-only coding input while retail rows remain ordinary transactions.

from __future__ import annotations

from pathlib import Path

from gdc_data_utils import ConditionClaim

from adapter_ingestion.manufacturers.api_config import ApiConfigAdapter
from adapter_ingestion.models import AdapterContext
from adapter_ingestion.service.api_config import deep_merge_dicts, extract_embedded_api_config
from adapter_ingestion.service.defaults import load_software_id_preset


REAL_QVET_WORKBOOK = Path(__file__).resolve().parents[2] / "examples" / "Qvet-api-config.xlsx"


def _context(schema_config: dict) -> AdapterContext:
    return AdapterContext(
        manufacturer="api-config",
        tenant_id="tenant-test",
        jurisdiction="CA-BC",
        sector="animal-care",
        issuer_did="did:web:issuer.example",
        audience_did="did:web:audience.example",
        data_use="secondary",
        schema_config=schema_config,
        strict_species_mapping=False,
        personal_id_resolver=lambda value: "00000000-0000-4000-8000-000000000001",
    )


def test_qvet_preset_extracts_only_explicit_clinical_condition_signals(tmp_path: Path) -> None:
    workbook = tmp_path / "qvet-api-config.csv"
    workbook.write_text(
        "API-CONFIG:version=1.3:language=es:software-id=qvet\n"
        ",concept,personal_id,section,family,encounter_service-type\n"
        "EMPRESA,CONCEPTO,CHIP,SECCION,FAMILIA,Descripcion2\n"
        "Clinic,APOQUEL,chip-1,clinica,MEDICAMENTOS,CONSULTA SEGUIMIENTO ALERGIA\n"
        "Clinic,ALIMENTO,chip-2,tienda,ALIMENTACION,VARIOS ALIMENTACION\n",
        encoding="utf-8",
    )
    embedded = extract_embedded_api_config(workbook)
    preset = load_software_id_preset("qvet-v1")
    assert embedded is not None
    assert preset is not None
    config = deep_merge_dicts(preset, embedded)

    records = ApiConfigAdapter().read_records(workbook, _context(config["schemaConfig"]))

    assert records[0].coding_inputs == {
        ConditionClaim.CODE: "CONSULTA SEGUIMIENTO ALERGIA",
    }
    assert records[1].coding_inputs == {}


def test_real_qvet_workbook_yields_bounded_condition_review_inputs() -> None:
    embedded = extract_embedded_api_config(REAL_QVET_WORKBOOK)
    preset = load_software_id_preset("qvet-v1")
    assert embedded is not None
    assert preset is not None
    config = deep_merge_dicts(preset, embedded)

    records = ApiConfigAdapter().read_records(
        REAL_QVET_WORKBOOK,
        _context(config["schemaConfig"]),
    )
    coding_inputs = [
        record.coding_inputs[ConditionClaim.CODE]
        for record in records
        if ConditionClaim.CODE in record.coding_inputs
    ]

    assert coding_inputs
    assert len(coding_inputs) < len(records)
    assert any("ALERGIA" in value for value in coding_inputs)
