# Flow contract: reuse canonical claim catalogs; preserve Invoice and ChargeItem FHIR relationship semantics.

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from types import SimpleNamespace

import pytest
from gdc_data_utils import ChargeItemClaim, InvoiceClaim

from adapter_ingestion.ai.base import NoopCodingAssistant
from adapter_ingestion.manufacturers.registry import get_adapter
from adapter_ingestion.models import AdapterContext
from adapter_ingestion.pipeline import run_pipeline
from adapter_ingestion.runtime.adapters import InMemorySearchRepository
from adapter_ingestion.service.api_config import extract_embedded_api_config
from adapter_ingestion.service.managers.conversion_search import ConversionSearchManager
from adapter_ingestion.service.research import build_storage_namespace
from adapter_ingestion.service.api_support import HTTPException


def _context(schema_config: dict) -> AdapterContext:
    return AdapterContext(
        manufacturer="api-config",
        tenant_id="financial-contract",
        jurisdiction="ES",
        sector="research",
        issuer_did="did:web:issuer.example",
        audience_did="did:web:audience.example",
        subject_did_prefix="urn:uuid",
        subject_kind="animal",
        strict_species_mapping=False,
        data_use="secondary",
        schema_config=schema_config,
    )


def test_api_config_materializes_invoice_and_charge_items_with_standard_links() -> None:
    csv_text = (
        "API-CONFIG:language=es:subjectKind=animal:dataUse=secondary\n"
        "date,subject_id,section,family,Invoice.identifier,Invoice.date,"
        "ChargeItem.identifier,ChargeItem.code,ChargeItem.code-text,"
        "ChargeItem.occurrence,ChargeItem.quantity-number,ChargeItem.quantity-unit\n"
        "FECHA,SUJETO,SECCION,FAMILIA,FACTURA,FECHA_FACTURA,LINEA,CODIGO,"
        "TEXTO,APLICADO,CANTIDAD,UNIDAD\n"
        "2026-03-19,11111111-1111-4111-8111-111111111111,clinica,factura,"
        "invoice-001,2026-03-19,charge-001,SVC-1,Consulta,2026-03-19,1,ea\n"
        "2026-03-19,11111111-1111-4111-8111-111111111111,clinica,factura,"
        "invoice-001,2026-03-19,charge-002,MED-1,Medicamento,2026-04-02,2,box\n"
    )
    with NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        tmp.write(csv_text)
        path = Path(tmp.name)
    try:
        embedded = extract_embedded_api_config(path)
        assert embedded is not None
        records = get_adapter("api-config").read_records(
            path,
            _context(embedded["schemaConfig"]),
        )
    finally:
        path.unlink(missing_ok=True)

    result = run_pipeline(records, _context(embedded["schemaConfig"]), NoopCodingAssistant())
    aggregate = result.composition_message["body"]["data"][0]["resource"]
    invoice = next(item for item in aggregate["contained"] if item.get("resourceType") == "Invoice")
    charge_items = [
        item for item in aggregate["contained"] if item.get("resourceType") == "ChargeItem"
    ]

    assert invoice["meta"]["claims"][InvoiceClaim.IDENTIFIER] == "invoice-001"
    assert [line["chargeItemReference"]["reference"] for line in invoice["lineItem"]] == [
        f"urn:uuid:{item['id']}" for item in charge_items
    ]
    assert len(charge_items) == 2
    for item in charge_items:
        claims = item["meta"]["claims"]
        assert claims[ChargeItemClaim.SUPPORTING_INFORMATION] == f"urn:uuid:{invoice['id']}"
        assert ChargeItemClaim.PART_OF not in claims
        assert item["supportingInformation"] == [{"reference": f"urn:uuid:{invoice['id']}"}]
        assert item["occurrenceDateTime"] == claims[ChargeItemClaim.OCCURRENCE]

    repository = InMemorySearchRepository()
    vault_id = build_storage_namespace(
        network_kind="test",
        jurisdiction="ES",
        sector="research",
        tenant_id="financial-contract",
    )
    for item in [invoice, *charge_items]:
        repository.upsert(
            vault_id=vault_id,
            resource_type=item["resourceType"],
            resource=item,
        )
    bundle = ConversionSearchManager(
        SimpleNamespace(settings=SimpleNamespace(demo_mode=True, network_mode="test"), search_repo=repository)
    ).handle(
        tenant_id="financial-contract",
        jurisdiction="ES",
        sector="research",
        resource_type="ChargeItem",
        response=SimpleNamespace(),
        request=SimpleNamespace(headers={}, query_params={}),
        body={
            "resourceType": "Parameters",
            "parameter": [
                {"name": "code", "valueString": "SVC-1,MED-1"},
                {"name": "occurrence", "valueDate": "ge2026-03-01"},
                {"name": "occurrence", "valueDate": "le2026-03-31"},
            ],
        },
    )
    assert bundle["type"] == "searchset"
    assert bundle["total"] == 1
    assert bundle["entry"][0]["resource"]["resourceType"] == "ChargeItem"


def test_financial_search_rejects_extension_fields_not_advertised_as_hl7_parameters() -> None:
    manager = ConversionSearchManager(
        SimpleNamespace(
            settings=SimpleNamespace(demo_mode=True),
            search_repo=InMemorySearchRepository(),
        )
    )
    with pytest.raises(HTTPException) as error:
        manager.handle(
            tenant_id="financial-contract",
            jurisdiction="ES",
            sector="research",
            resource_type="ChargeItem",
            response=SimpleNamespace(),
            request=SimpleNamespace(headers={}, query_params={}),
            body={
                "resourceType": "Parameters",
                "parameter": [
                    {"name": "supplier-productcode", "valueString": "supplier-1"},
                ],
            },
        )

    assert error.value.status_code == 400
    assert "supported FHIR R4 search parameter" in str(error.value.detail)
