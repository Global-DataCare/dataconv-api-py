# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse
import json
import unicodedata

from .ai import NoopCodingAssistant, RuleBasedCodingAssistant
from .models import AdapterContext
from .gateway_client import post_didcomm_plaintext
from .manufacturers import get_adapter, list_adapters
from .pipeline import run_pipeline
from .service.api_config import deep_merge_dicts, extract_embedded_api_config


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_local_species(value: str) -> str:
    normalized = unicodedata.normalize("NFD", str(value or ""))
    without_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return " ".join(without_accents.strip().lower().split())


def _load_json_file(path_value: str) -> dict[str, Any]:
    if not path_value:
        return {}
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def _load_species_catalog(path_value: str) -> tuple[str, dict[str, str]]:
    data = _load_json_file(path_value)
    if not data:
        return ("http://hl7.org/fhir/target-species", {})

    if "codes" in data and isinstance(data["codes"], dict):
        system = str(data.get("system", "http://hl7.org/fhir/target-species"))
        catalog = {
            str(code).strip(): str(display).strip()
            for code, display in data["codes"].items()
            if str(code).strip()
        }
        return (system, catalog)

    # fallback: assume direct code -> display object
    catalog = {str(code).strip(): str(display).strip() for code, display in data.items() if str(code).strip()}
    return ("http://hl7.org/fhir/target-species", catalog)


def _load_species_local_map(path_value: str) -> dict[str, str]:
    data = _load_json_file(path_value)
    if not data:
        return {}

    if not isinstance(data.get("speciesLocalToFhirCode"), dict):
        raise ValueError(
            "species-local-map must include an object property 'speciesLocalToFhirCode'"
        )
    mapping_source = data.get("speciesLocalToFhirCode")

    mapping: dict[str, str] = {}
    for local_label, fhir_code in mapping_source.items():
        local_text = str(local_label).strip()
        code_text = str(fhir_code).strip()
        if not local_text:
            continue
        mapping[local_text] = code_text
        mapping[local_text.upper()] = code_text
        mapping[_normalize_local_species(local_text)] = code_text
    return mapping


def _export_species_template(path_value: str, context: AdapterContext, adapter_report: dict[str, Any]) -> None:
    if not path_value:
        return
    output_path = Path(path_value).expanduser().resolve()
    species_counts = adapter_report.get("speciesCounts", {}) if isinstance(adapter_report, dict) else {}
    unmapped_counts = adapter_report.get("unmappedSpeciesCounts", {}) if isinstance(adapter_report, dict) else {}

    local_to_fhir: dict[str, str] = {}
    for local_label in species_counts.keys():
        local_to_fhir[local_label] = context.species_local_to_fhir.get(local_label, "")

    payload = {
        "system": context.fhir_species_system,
        "codes": context.fhir_species_catalog,  # FHIR code -> english display
        "speciesLocalToFhirCode": local_to_fhir,  # clinic local label -> FHIR code
        "localSpeciesCounts": species_counts,
        "unmappedSpeciesCounts": unmapped_counts,
    }
    _write_json(output_path, payload)


def _artifact_output_dir(base_dir: str, input_path: Path) -> Path:
    base_path = Path(base_dir).expanduser().resolve()
    stem = input_path.stem.strip() or "conversion"
    if base_path.name == stem:
        return base_path
    return base_path / stem


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="External ingestion adapter runner.")
    parser.add_argument("--manufacturer", required=True, choices=list_adapters())
    parser.add_argument("--input", required=True, help="Input file path (vendor export).")
    parser.add_argument("--tenant-id", default="", help="Legacy route segment (optional).")
    parser.add_argument("--jurisdiction", default="", help="Legacy route segment (optional).")
    parser.add_argument("--sector", default="", help="Legacy route segment (optional).")
    parser.add_argument("--issuer-did", required=True)
    parser.add_argument("--audience-did", required=True)
    parser.add_argument("--language", default="es-ES")
    parser.add_argument(
        "--data-use",
        choices=["secondary", "individual"],
        default="secondary",
        help="Use 'secondary' for anonymized twin/research payloads (no narrative text).",
    )
    parser.add_argument("--gateway-base-url", default="http://localhost:3000")
    parser.add_argument(
        "--resource-route-prefix",
        default="/v1",
        help=(
            "Base prefix for send routes when tenant/jurisdiction/sector are empty. "
            "Example: /v1"
        ),
    )
    parser.add_argument("--output-dir", default="./artifacts")
    parser.add_argument("--coding-provider", choices=["noop", "rules"], default="noop")
    parser.add_argument(
        "--species-catalog-file",
        default="",
        help="JSON with FHIR species catalog (code -> english display).",
    )
    parser.add_argument(
        "--species-local-map-file",
        default="",
        help="JSON with clinic mapping (speciesLocalToFhirCode).",
    )
    parser.add_argument(
        "--allow-unmapped-species",
        action="store_true",
        help="Do not fail when ESPECIE values are not mapped.",
    )
    parser.add_argument(
        "--export-species-template",
        default="",
        help="Write local ESPECIE aggregates + mapping template JSON to this path.",
    )
    parser.add_argument(
        "--subject-did-prefix",
        default="did:web:example.org",
        help="Prefix for subject DID, e.g. did:web:animals.example.com:acme",
    )
    parser.add_argument(
        "--subject-kind",
        choices=["animal", "species"],
        default="animal",
        help="Use fixed 'animal' segment or species-specific segment in DID path.",
    )
    parser.add_argument(
        "--include-fields",
        default="",
        help="Comma-separated source column names included in XHTML table. Empty means all columns.",
    )
    parser.add_argument(
        "--schema-config-file",
        default="",
        help=(
            "JSON file with tabular schema mapping overrides, e.g. "
            "headerRowIndex, fieldMap.{concept,species,family,...}, speciesContains."
        ),
    )
    parser.add_argument(
        "--embed-xhtml-content",
        action="store_true",
        help=(
            "Deprecated (no-op). XHTML narrative is stored in DocumentReference.text; "
            "DocumentReference.content* is reserved for real attachments."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Build artifacts only.")
    parser.add_argument("--send", action="store_true", help="Send generated messages to gateway.")
    parser.add_argument("--auth-token", default="", help="Bearer token used when --send is enabled.")
    return parser


def _resource_route(
    resource_type: str,
    tenant_id: str = "",
    jurisdiction: str = "",
    sector: str = "",
    route_prefix: str = "/v1",
) -> str:
    tenant = str(tenant_id or "").strip()
    juris = str(jurisdiction or "").strip()
    sec = str(sector or "").strip()
    if tenant and juris and sec:
        return (
            f"/{tenant}/cds-{juris}/v1/{sec}/"
            f"individual/org.hl7.fhir.r4/{resource_type}/_batch"
        )

    prefix = str(route_prefix or "").strip()
    if prefix and not prefix.startswith("/"):
        prefix = "/" + prefix
    prefix = prefix.rstrip("/")
    if not prefix:
        return f"/individual/org.hl7.fhir.r4/{resource_type}/_batch"
    return f"{prefix}/individual/org.hl7.fhir.r4/{resource_type}/_batch"


def main() -> int:
    args = _build_parser().parse_args()
    if args.embed_xhtml_content:
        print(
            "warning: --embed-xhtml-content is deprecated and has no effect. "
            "Use DocumentReference.content* only for real attachments."
        )

    include_fields = tuple(
        field.strip().upper()
        for field in str(args.include_fields or "").split(",")
        if field.strip()
    )
    loaded_schema_payload = _load_json_file(args.schema_config_file)
    embedded_config = extract_embedded_api_config(Path(args.input).expanduser().resolve())
    effective_config_payload = (
        deep_merge_dicts(embedded_config, loaded_schema_payload)
        if embedded_config
        else loaded_schema_payload
    )
    schema_config = effective_config_payload.get("schemaConfig", {}) if isinstance(effective_config_payload, dict) else {}
    species_system, species_catalog = _load_species_catalog(args.species_catalog_file)
    species_local_map = _load_species_local_map(args.species_local_map_file)

    if species_catalog:
        invalid_codes = sorted({code for code in species_local_map.values() if code and code not in species_catalog})
        if invalid_codes:
            sample = ", ".join(invalid_codes[:20])
            raise ValueError(
                "species-local-map contains codes not present in species-catalog: "
                f"{sample}"
            )

    strict_species_mapping = (not args.allow_unmapped_species) and (not args.export_species_template)

    context = AdapterContext(
        manufacturer=args.manufacturer,
        tenant_id=args.tenant_id,
        jurisdiction=args.jurisdiction,
        sector=args.sector,
        issuer_did=args.issuer_did,
        audience_did=args.audience_did,
        language=(
            str((effective_config_payload.get("runtimeDefaults", {}) if isinstance(effective_config_payload, dict) else {}).get("language", "")).strip()
            or args.language
        ),
        gateway_base_url=args.gateway_base_url,
        subject_did_prefix=args.subject_did_prefix,
        subject_kind=args.subject_kind,
        include_fields=include_fields,
        fhir_species_system=species_system,
        fhir_species_catalog=species_catalog,
        species_local_to_fhir=species_local_map,
        strict_species_mapping=strict_species_mapping,
        schema_config=schema_config,
        embed_xhtml_content=args.embed_xhtml_content,
        data_use=args.data_use,
    )

    adapter = get_adapter(args.manufacturer)
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    coding_assistant = RuleBasedCodingAssistant() if args.coding_provider == "rules" else NoopCodingAssistant()
    records = adapter.read_records(input_path=input_path, context=context)
    adapter_report = adapter.get_last_report() if hasattr(adapter, "get_last_report") else {}
    row_issues = adapter_report.get("rowIssues", []) if isinstance(adapter_report, dict) else []
    result = run_pipeline(
        records=records,
        context=context,
        coding_assistant=coding_assistant,
        row_issues=row_issues if isinstance(row_issues, list) else [],
    )
    if adapter_report:
        result.summary["adapterReport"] = adapter_report
    _export_species_template(args.export_species_template, context, adapter_report)

    output_dir = _artifact_output_dir(args.output_dir, input_path)
    _write_json(output_dir / "composition-message.json", result.composition_message)
    _write_json(output_dir / "summary.json", result.summary)
    stale_doc_file = output_dir / "documentreference-message.json"
    if stale_doc_file.exists():
        stale_doc_file.unlink()

    print(f"adapter: {args.manufacturer}")
    print(f"records: {result.summary['recordsTotal']}")
    print(f"subjects: {result.summary['subjectsTotal']}")
    print(f"subject entries: {result.summary.get('subjectEntries', 0)}")
    print(f"patient entries: {result.summary.get('patientEntries', 0)}")
    print(f"documentReference entries: {result.summary['documentReferenceEntries']}")
    print(f"encounter entries: {result.summary.get('encounterEntries', 0)}")
    print(f"relatedPerson entries: {result.summary.get('relatedPersonEntries', 0)}")
    print(f"composition entries: {result.summary['compositionEntries']}")
    print(f"artifacts: {output_dir}")

    if args.send:
        if not args.auth_token:
            raise ValueError("--auth-token is required when --send is used.")

        first_entry = (
            result.composition_message.get("body", {}).get("data", [])[0]
            if isinstance(result.composition_message.get("body", {}).get("data", []), list)
            and result.composition_message.get("body", {}).get("data")
            else {}
        )
        primary_resource_type = (
            str(first_entry.get("resource", {}).get("resourceType", "")).strip()
            if isinstance(first_entry, dict)
            else ""
        )
        if not primary_resource_type:
            primary_resource_type = "Patient"

        comp_route = _resource_route(
            resource_type=primary_resource_type,
            tenant_id=args.tenant_id,
            jurisdiction=args.jurisdiction,
            sector=args.sector,
            route_prefix=args.resource_route_prefix,
        )

        comp_response = post_didcomm_plaintext(
            base_url=args.gateway_base_url,
            route_path=comp_route,
            bearer_token=args.auth_token,
            payload=result.composition_message,
        )
        print(f"POST {comp_route} -> {comp_response.status} location={comp_response.location or '-'}")
    elif args.dry_run:
        print("dry-run enabled, messages were not sent.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
