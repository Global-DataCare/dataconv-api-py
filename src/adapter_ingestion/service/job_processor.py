# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
import json
import unicodedata
import uuid
from hashlib import sha256

from ..ai.base import NoopCodingAssistant
from ..models import AdapterContext
from ..manufacturers import get_adapter
from ..pipeline import run_pipeline
from ..runtime import BlobStore, ConfigKey, IVaultRepository, PreconversionControlPlane
from .api_support import _compose_software_id_token
from .observability import log_event
from .research import DEFAULT_SECTOR, build_vault_id
from .research_drafts import annotate_composition_message_for_research, persist_research_drafts
from .settings import ServiceSettings

PERSONAL_ID_ALIAS_SECTION = "personal-id-alias"


def _species_catalog_from_config(raw: dict[str, Any]) -> tuple[str, dict[str, str]]:
    if not isinstance(raw, dict):
        return ("http://hl7.org/fhir/target-species", {})
    system = str(raw.get("system", "http://hl7.org/fhir/target-species"))
    codes = raw.get("codes", {})
    catalog: dict[str, str] = {}
    if isinstance(codes, dict):
        for code, display in codes.items():
            code_text = str(code).strip()
            display_text = str(display).strip()
            if code_text and display_text:
                catalog[code_text] = display_text
    return (system, catalog)


def _species_catalog_from_file(path_value: str) -> tuple[str, dict[str, str]]:
    path = Path(str(path_value or "").strip()).expanduser()
    if not path.exists():
        return ("http://hl7.org/fhir/target-species", {})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ("http://hl7.org/fhir/target-species", {})
    return _species_catalog_from_config(data if isinstance(data, dict) else {})


def _normalize_local_species(value: str) -> str:
    normalized = unicodedata.normalize("NFD", str(value or ""))
    without_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return " ".join(without_accents.strip().lower().split())


def _species_local_map_from_config(raw: dict[str, Any]) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    mapping_source = raw.get("speciesLocalToFhirCode", {})
    if not isinstance(mapping_source, dict):
        return {}

    mapping: dict[str, str] = {}
    for local_label, fhir_code in mapping_source.items():
        local_text = str(local_label).strip()
        code_text = str(fhir_code).strip()
        if not local_text or not code_text:
            continue
        mapping[local_text] = code_text
        mapping[local_text.upper()] = code_text
        mapping[_normalize_local_species(local_text)] = code_text
    return mapping


def _include_fields_from_runtime_defaults(raw: dict[str, Any]) -> tuple[str, ...]:
    fields = raw.get("includeFields", [])
    if not isinstance(fields, list):
        return tuple()
    return tuple(str(item).strip().upper() for item in fields if str(item).strip())


def _language_from_country(country: str) -> str:
    raw = str(country or "").strip()
    if not raw:
        return "es-ES"

    normalized = raw.replace("_", "-").strip()
    if "-" in normalized:
        parts = [part for part in normalized.split("-") if part]
        if len(parts) >= 2:
            return f"{parts[0].lower()}-{parts[1].upper()}"

    key = normalized.lower()
    mapping = {
        "es": "es-ES",
        "mx": "es-MX",
        "ar": "es-AR",
        "co": "es-CO",
        "cl": "es-CL",
        "pe": "es-PE",
        "uy": "es-UY",
        "br": "pt-BR",
        "pt": "pt-PT",
        "fr": "fr-FR",
        "de": "de-DE",
        "it": "it-IT",
        "nl": "nl-NL",
        "be": "fr-BE",
        "gb": "en-GB",
        "uk": "en-GB",
        "us": "en-US",
    }
    if key in mapping:
        return mapping[key]

    return f"{key.lower()}-{key.upper()}" if len(key) == 2 else "es-ES"


def _build_context(
    *,
    settings: ServiceSettings,
    request_alternate_name: str,
    request_country: str,
    request_manufacturer: str,
    config_payload: dict[str, Any],
    vault_repo: IVaultRepository | None = None,
    settings_target_sector: str = DEFAULT_SECTOR,
) -> AdapterContext:
    runtime_defaults = (
        config_payload.get("runtimeDefaults", {})
        if isinstance(config_payload.get("runtimeDefaults"), dict)
        else {}
    )
    schema_config = config_payload.get("schemaConfig", {})
    # Canonical key: speciesFhir. Keep speciesCatalog as temporary backward-compat fallback.
    species_catalog_raw = config_payload.get("speciesFhir", {})
    if not isinstance(species_catalog_raw, dict):
        species_catalog_raw = {}
    if not species_catalog_raw and isinstance(config_payload.get("speciesCatalog"), dict):
        species_catalog_raw = config_payload.get("speciesCatalog", {})
    species_system, species_catalog = _species_catalog_from_config(species_catalog_raw)
    if not species_catalog:
        species_system, species_catalog = _species_catalog_from_file(settings.default_species_fhir_file)
    species_local_map = _species_local_map_from_config(config_payload)

    issuer_did = str(runtime_defaults.get("issuerDid", "")).strip() or settings.default_issuer_did
    audience_did = str(runtime_defaults.get("audienceDid", "")).strip() or settings.default_audience_did
    subject_did_prefix = (
        str(runtime_defaults.get("subjectDidPrefix", "")).strip() or settings.default_subject_did_prefix
    )

    language = str(runtime_defaults.get("language", "")).strip() or _language_from_country(request_country)
    resolved_sector = str(config_payload.get("targetSector") or settings_target_sector or DEFAULT_SECTOR).strip() or DEFAULT_SECTOR
    vault_id = build_vault_id(
        sector=resolved_sector,
        tenant_id=request_alternate_name,
    )

    def _personal_id_resolver(raw_personal_id: str) -> str:
        personal_id = str(raw_personal_id or "").strip()
        if not personal_id or vault_repo is None:
            return ""
        seed = f"urn:globaldatacare:{resolved_sector}:{request_alternate_name}:personal-id:{personal_id}"
        lookup_hash = sha256(seed.encode("utf-8")).hexdigest()
        found = vault_repo.get(vault_id, lookup_hash, PERSONAL_ID_ALIAS_SECTION)
        if isinstance(found, dict):
            found_uuid = str(found.get("uuid", "")).strip()
            if found_uuid:
                return found_uuid
        pseudonym_uuid = str(uuid.uuid4())
        vault_repo.put(
            vault_id,
            [
                {
                    "id": lookup_hash,
                    "type": "personal-id-alias",
                    "lookupHash": lookup_hash,
                    "uuid": pseudonym_uuid,
                }
            ],
            PERSONAL_ID_ALIAS_SECTION,
        )
        return pseudonym_uuid

    return AdapterContext(
        manufacturer=request_manufacturer,
        tenant_id=request_alternate_name,
        jurisdiction=request_country,
        sector=resolved_sector,
        issuer_did=issuer_did,
        audience_did=audience_did,
        language=language,
        gateway_base_url=str(runtime_defaults.get("gatewayBaseUrl", "http://localhost:3000")).strip()
        or "http://localhost:3000",
        subject_did_prefix=subject_did_prefix,
        subject_kind=str(runtime_defaults.get("subjectKind", "animal")).strip() or "animal",
        include_fields=_include_fields_from_runtime_defaults(runtime_defaults),
        fhir_species_system=species_system,
        fhir_species_catalog=species_catalog,
        species_local_to_fhir=species_local_map,
        strict_species_mapping=False,
        schema_config=schema_config if isinstance(schema_config, dict) else {},
        personal_id_resolver=_personal_id_resolver if vault_repo is not None else None,
        embed_xhtml_content=bool(runtime_defaults.get("embedXhtmlContent", False)),
        data_use=str(runtime_defaults.get("dataUse", "secondary")).strip() or "secondary",
    )


def _build_output_payload(
    *,
    composition_message: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, bytes]:
    return {
        "composition-message.json": json.dumps(
            composition_message, ensure_ascii=False, indent=2
        ).encode("utf-8"),
        "summary.json": json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8"),
    }


def _input_suffix_from_ref(input_ref: str) -> str:
    text = str(input_ref or "").strip()
    if text.startswith("gs://"):
        _, _, rest = text.partition("gs://")
        _, _, path = rest.partition("/")
        name = path.rsplit("/", 1)[-1] if path else "input.xlsx"
        return Path(name).suffix or ".xlsx"
    if text.startswith("file://"):
        text = text[len("file://") :]
    return Path(text).suffix or ".xlsx"


def _job_log_fields(job: Any) -> dict[str, Any]:
    manufacturer = str(job.request.manufacturer or "").strip()
    manufacturer_version = str(job.request.manufacturer_version or "").strip()
    software_id = f"{manufacturer}-{manufacturer_version}" if manufacturer and manufacturer_version else manufacturer
    return {
        "jobId": str(job.job_id or "").strip(),
        "thid": str(job.thid or "").strip(),
        "tenantId": str(job.request.alternate_name or "").strip(),
        "manufacturer": manufacturer,
        "manufacturerVersion": manufacturer_version,
        "softwareId": software_id,
        "country": str(job.request.country or "").strip(),
        "mode": str(job.request.mode or "").strip(),
    }


def process_one_job(
    *,
    control_plane: PreconversionControlPlane,
    blob_store: BlobStore,
    vault_repo: IVaultRepository,
    settings: ServiceSettings,
    worker_id: str,
) -> str | None:
    job = control_plane.claim_next_job(worker_id=worker_id)
    if not job:
        return None
    log_event("job_processing_started", workerId=worker_id, **_job_log_fields(job))

    try:
        if job.request.mode == "demo-ephemeral":
            config_payload = dict(job.request.inline_config or {})
        else:
            if not job.config_key_used:
                raise RuntimeError("No configuration found for job selector.")
            resolved = control_plane.resolve_config(job.config_key_used)
            if not resolved:
                raise RuntimeError("Configuration disappeared while processing job.")
            config_payload = dict(resolved.content or {})

        input_bytes = blob_store.get_bytes(job.request.input_ref)
        suffix = _input_suffix_from_ref(job.request.input_ref)
        with NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(input_bytes)
            tmp_path = Path(tmp.name)

        context = _build_context(
            settings=settings,
            request_alternate_name=job.request.alternate_name,
            request_country=job.request.country,
            request_manufacturer=job.request.manufacturer,
            config_payload=config_payload,
            vault_repo=vault_repo,
            settings_target_sector=job.request.sector,
        )
        adapter = get_adapter(job.request.manufacturer)
        records = adapter.read_records(input_path=tmp_path, context=context)
        adapter_report = adapter.get_last_report() if hasattr(adapter, "get_last_report") else {}
        row_issues = adapter_report.get("rowIssues", []) if isinstance(adapter_report, dict) else []
        result = run_pipeline(
            records=records,
            context=context,
            coding_assistant=NoopCodingAssistant(),
            row_issues=row_issues if isinstance(row_issues, list) else [],
        )
        if isinstance(adapter_report, dict) and adapter_report:
            result.summary["adapterReport"] = adapter_report
        annotated_message = annotate_composition_message_for_research(result.composition_message, user_selected=True)
        draft_count = persist_research_drafts(
            vault_repo=vault_repo,
            job=job,
            jurisdiction=job.request.country,
            composition_message=annotated_message,
        )
        result.summary["researchDraftsPersisted"] = int(draft_count)
        result.summary["vaultId"] = build_vault_id(sector=job.request.sector, tenant_id=job.request.alternate_name)
        result.summary["softwareId"] = _compose_software_id_token(
            job.request.manufacturer,
            job.request.manufacturer_version,
        )

        output_payloads = _build_output_payload(
            composition_message=annotated_message,
            summary=result.summary,
        )
        base_path = f"jobs/{job.job_id}"
        refs: dict[str, str] = {}
        for name, payload in output_payloads.items():
            refs[name] = blob_store.put_bytes(
                path=f"{base_path}/{name}",
                payload=payload,
                content_type="application/json",
            )

        result_ref = refs.get("summary.json", "")
        updated = control_plane.mark_job_succeeded(job.job_id, result_ref=result_ref)
        log_event(
            "job_processing_succeeded",
            workerId=worker_id,
            resultRef=result_ref,
            **_job_log_fields(updated),
        )
        return job.job_id
    except Exception as exc:
        updated = control_plane.mark_job_failed(job.job_id, error=str(exc))
        log_event(
            "job_processing_failed",
            workerId=worker_id,
            error=str(exc),
            **_job_log_fields(updated),
        )
        return job.job_id
    finally:
        try:
            if "tmp_path" in locals() and tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
