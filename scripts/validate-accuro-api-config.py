#!/usr/bin/env python3
# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from gdc_data_utils import ChargeItemClaim, DiagnosticReportClaim, InvoiceClaim

from adapter_ingestion.accuro_workbook import ACCURO_SHEET_CONFIGS
from adapter_ingestion.ai.base import NoopCodingAssistant
from adapter_ingestion.manufacturers.registry import get_adapter
from adapter_ingestion.models import AdapterContext
from adapter_ingestion.pipeline import run_pipeline
from adapter_ingestion.runtime.adapters import InMemorySearchRepository
from adapter_ingestion.service.api_config import extract_embedded_api_config
from adapter_ingestion.service.managers.conversion_search import ConversionSearchManager


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate every prepared Accuro organization workbook and one FHIR search per sheet."
    )
    parser.add_argument("split_dir", type=Path)
    parser.add_argument("--preparation-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    preparation = json.loads(args.preparation_report.read_text(encoding="utf-8"))
    validation: dict[str, object] = {"sheets": {}}
    sheets = validation["sheets"]
    assert isinstance(sheets, dict)

    for config in ACCURO_SHEET_CONFIGS:
        workbook_path = args.split_dir / f"{config.slug}.xlsx"
        embedded = extract_embedded_api_config(workbook_path)
        if not embedded:
            raise AssertionError(f"Missing API-CONFIG in {workbook_path}")
        context = AdapterContext(
            manufacturer=config.software_id,
            tenant_id=config.slug,
            jurisdiction="ES",
            sector="onehealth-research",
            issuer_did="did:web:issuer.example",
            audience_did="did:web:audience.example",
            subject_did_prefix="urn:uuid",
            subject_kind=config.subject_kind,
            strict_species_mapping=False,
            schema_config=embedded["schemaConfig"],
            data_use="secondary",
        )
        records = get_adapter("api-config").read_records(workbook_path, context)
        expected_rows = int(preparation["sheets"][config.name]["sourceRows"])
        if len(records) != expected_rows:
            raise AssertionError(f"{config.name}: expected {expected_rows} records, received {len(records)}")
        subject_identifiers = {record.subject_id for record in records}
        for identifier in subject_identifiers:
            if not identifier.startswith("urn:uuid:"):
                raise AssertionError(f"{config.name}: invalid ResearchSubject identifier {identifier}")
            UUID(identifier.removeprefix("urn:uuid:"))

        sample_records = records[: min(10, len(records))]
        pipeline_result = run_pipeline(sample_records, context, NoopCodingAssistant())
        research_subjects = [
            entry["resource"]
            for entry in pipeline_result.composition_message["body"]["data"]
            if entry.get("resource", {}).get("resourceType") == "ResearchSubject"
        ]
        if not research_subjects:
            raise AssertionError(f"{config.name}: pipeline produced no ResearchSubject")
        first = research_subjects[0]
        identifier = first["meta"]["claims"]["ResearchSubject.identifier"]
        repository = InMemorySearchRepository()
        vault_id = f"{context.sector}_{context.tenant_id}"
        repository.upsert(vault_id=vault_id, resource_type="ResearchSubject", resource=first)
        repository.upsert(vault_id=vault_id, resource_type="ResearchSubject", resource=first)
        result = ConversionSearchManager(
            SimpleNamespace(settings=SimpleNamespace(demo_mode=True), search_repo=repository)
        ).handle(
            tenant_id=context.tenant_id,
            jurisdiction=context.jurisdiction,
            sector=context.sector,
            resource_type="ResearchSubject",
            response=SimpleNamespace(),
            request=SimpleNamespace(headers={}, query_params={}),
            body={
                "resourceType": "Parameters",
                "parameter": [{"name": "identifier", "valueUri": identifier}],
            },
        )
        if result.get("resourceType") != "Bundle" or result.get("type") != "searchset" or result.get("total") != 1:
            raise AssertionError(f"{config.name}: idempotent FHIR search contract failed")
        diagnostic_reports = [
            resource
            for subject in research_subjects
            for resource in subject.get("contained", [])
            if isinstance(resource, dict) and resource.get("resourceType") == "DiagnosticReport"
        ]
        diagnostic_search_matches = 0
        if diagnostic_reports:
            diagnostic_report = diagnostic_reports[0]
            diagnosis_text = str(
                diagnostic_report.get("meta", {}).get("claims", {}).get(
                    DiagnosticReportClaim.CODE_TEXT,
                    "",
                )
            )
            repository.upsert(
                vault_id=vault_id,
                resource_type="DiagnosticReport",
                resource=diagnostic_report,
            )
            diagnostic_result = ConversionSearchManager(
                SimpleNamespace(settings=SimpleNamespace(demo_mode=True), search_repo=repository)
            ).handle(
                tenant_id=context.tenant_id,
                jurisdiction=context.jurisdiction,
                sector=context.sector,
                resource_type="DiagnosticReport",
                response=SimpleNamespace(),
                request=SimpleNamespace(headers={}, query_params={}),
                body={
                    "resourceType": "Parameters",
                    "parameter": [
                        {"name": "code:text", "valueString": diagnosis_text[:8]}
                    ],
                },
            )
            diagnostic_search_matches = int(diagnostic_result.get("total") or 0)
            if diagnostic_search_matches != 1:
                raise AssertionError(f"{config.name}: DiagnosticReport code:text search failed")
        invoices = [
            resource
            for subject in research_subjects
            for resource in subject.get("contained", [])
            if isinstance(resource, dict) and resource.get("resourceType") == "Invoice"
        ]
        charge_items = [
            resource
            for subject in research_subjects
            for resource in subject.get("contained", [])
            if isinstance(resource, dict) and resource.get("resourceType") == "ChargeItem"
        ]
        invoice_search_matches = 0
        charge_item_search_matches = 0
        if invoices:
            invoice = invoices[0]
            invoice_identifier = str(
                invoice.get("meta", {}).get("claims", {}).get(InvoiceClaim.IDENTIFIER, "")
            )
            repository.upsert(vault_id=vault_id, resource_type="Invoice", resource=invoice)
            invoice_result = ConversionSearchManager(
                SimpleNamespace(settings=SimpleNamespace(demo_mode=True), search_repo=repository)
            ).handle(
                tenant_id=context.tenant_id,
                jurisdiction=context.jurisdiction,
                sector=context.sector,
                resource_type="Invoice",
                response=SimpleNamespace(),
                request=SimpleNamespace(headers={}, query_params={}),
                body={
                    "resourceType": "Parameters",
                    "parameter": [{"name": "identifier", "valueString": invoice_identifier}],
                },
            )
            invoice_search_matches = int(invoice_result.get("total") or 0)
            if invoice_search_matches != 1:
                raise AssertionError(f"{config.name}: Invoice identifier search failed")
        if charge_items:
            charge_item = charge_items[0]
            charge_identifier = str(
                charge_item.get("meta", {}).get("claims", {}).get(
                    ChargeItemClaim.IDENTIFIER,
                    "",
                )
            )
            charge_occurrence = str(
                charge_item.get("meta", {}).get("claims", {}).get(
                    ChargeItemClaim.OCCURRENCE,
                    "",
                )
            )
            for resource in charge_items:
                repository.upsert(vault_id=vault_id, resource_type="ChargeItem", resource=resource)
            charge_result = ConversionSearchManager(
                SimpleNamespace(settings=SimpleNamespace(demo_mode=True), search_repo=repository)
            ).handle(
                tenant_id=context.tenant_id,
                jurisdiction=context.jurisdiction,
                sector=context.sector,
                resource_type="ChargeItem",
                response=SimpleNamespace(),
                request=SimpleNamespace(headers={}, query_params={}),
                body={
                    "resourceType": "Parameters",
                    "parameter": [
                        {"name": "identifier", "valueString": charge_identifier},
                        {"name": "occurrence", "valueString": f"ge{charge_occurrence}"},
                        {"name": "occurrence", "valueString": f"le{charge_occurrence}"},
                    ],
                },
            )
            charge_item_search_matches = int(charge_result.get("total") or 0)
            if charge_item_search_matches < 1:
                raise AssertionError(f"{config.name}: ChargeItem identifier search failed")
        sheets[config.name] = {
            "recordsImported": len(records),
            "uniqueResearchSubjects": len(subject_identifiers),
            "fhirParametersSearchMatches": result["total"],
            "duplicateAfterSecondUpsert": 0,
            "diagnosticReportSampleCount": len(diagnostic_reports),
            "diagnosticReportFhirSearchMatches": diagnostic_search_matches,
            "invoiceSampleCount": len(invoices),
            "invoiceFhirSearchMatches": invoice_search_matches,
            "chargeItemSampleCount": len(charge_items),
            "chargeItemFhirSearchMatches": charge_item_search_matches,
        }

    rendered = json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
