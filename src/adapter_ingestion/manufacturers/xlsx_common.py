# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile
import re
import unicodedata
import xml.etree.ElementTree as ET

NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

CELL_REF_RE = re.compile(r"([A-Z]+)(\d+)")
SPANISH_LONG_DATE_RE = re.compile(r"^\s*(\d{1,2})\s+de\s+([A-Za-z]+)\s+de\s+(\d{4})\s*$")
TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$")

SPANISH_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


@dataclass(frozen=True)
class ParsedRow:
    row_number: int
    values: dict[str, str]


def normalize_token(value: str) -> str:
    normalized = unicodedata.normalize("NFD", str(value or ""))
    without_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", without_accents).strip().lower()


def slug(value: str) -> str:
    base = normalize_token(value)
    slug_text = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return slug_text or "na"


def strip_list_artifacts(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()
    text = re.sub(r"(^['\"]+|['\"]+$)", "", text)
    text = re.sub(r"['\"]\s*,\s*['\"]", ", ", text)
    text = re.sub(r"['\"]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def birth_year(value: str) -> str:
    text = strip_list_artifacts(value)
    if not text:
        return ""
    match = re.search(r"\b(19|20)\d{2}\b", text)
    if match:
        return match.group(0)
    return ""


def normalize_gender_status(value: str) -> str:
    text = strip_list_artifacts(value)
    if not text:
        return ""

    normalized = normalize_token(text)
    if normalized in {"true", "1", "yes", "y", "si", "sí", "sterilized", "sterilised", "castrated", "spayed"}:
        return "neutered"
    if normalized in {"false", "0", "no", "n", "intact", "entero", "entera", "not neutered"}:
        return "intact"
    if normalized in {"neutered", "castrado", "castrada", "esterilizado", "esterilizada"}:
        return "neutered"
    return text


def _col_index(cell_ref: str) -> int | None:
    match = CELL_REF_RE.match(cell_ref or "")
    if not match:
        return None
    letters = match.group(1)
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - 64)
    return index - 1


def _itertext(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext())


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    value_type = cell.attrib.get("t")
    value_node = cell.find("main:v", NS)

    if value_type == "s" and value_node is not None and value_node.text is not None:
        idx = int(value_node.text)
        return shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
    if value_type == "inlineStr":
        return _itertext(cell.find("main:is", NS))
    return value_node.text.strip() if value_node is not None and value_node.text else ""


def read_xlsx_rows(file_path: Path, header_row_index: int = 1) -> list[ParsedRow]:
    if header_row_index < 1:
        raise ValueError("header_row_index must be >= 1")

    with ZipFile(file_path) as zip_file:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in zip_file.namelist():
            shared_root = ET.fromstring(zip_file.read("xl/sharedStrings.xml"))
            for item in shared_root.findall("main:si", NS):
                shared_strings.append(_itertext(item))

        workbook_root = ET.fromstring(zip_file.read("xl/workbook.xml"))
        rels_root = ET.fromstring(zip_file.read("xl/_rels/workbook.xml.rels"))
        rel_by_id = {
            rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_root.findall("pkgrel:Relationship", NS)
        }

        sheets = workbook_root.findall("main:sheets/main:sheet", NS)
        if not sheets:
            return []
        first_sheet = sheets[0]

        rel_id = first_sheet.attrib.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", ""
        )
        sheet_target = rel_by_id.get(rel_id, "")
        if not sheet_target:
            return []
        if not sheet_target.startswith("worksheets/"):
            sheet_target = "worksheets/" + Path(sheet_target).name

        sheet_root = ET.fromstring(zip_file.read("xl/" + sheet_target))
        rows = sheet_root.findall("main:sheetData/main:row", NS)
        if not rows:
            return []
        if header_row_index > len(rows):
            raise ValueError(
                f"header_row_index={header_row_index} is out of range for sheet with {len(rows)} rows"
            )

        header_zero = header_row_index - 1
        header_row = rows[header_zero]
        header_map: dict[int, str] = {}
        for cell in header_row.findall("main:c", NS):
            index = _col_index(cell.attrib.get("r", ""))
            if index is None:
                continue
            header_map[index] = _cell_value(cell, shared_strings).strip()

        parsed_rows: list[ParsedRow] = []
        for offset, row in enumerate(rows[header_zero + 1 :], start=1):
            row_values_by_index: dict[int, str] = {}
            for cell in row.findall("main:c", NS):
                index = _col_index(cell.attrib.get("r", ""))
                if index is None:
                    continue
                row_values_by_index[index] = _cell_value(cell, shared_strings)

            parsed_row: dict[str, str] = {}
            for index, header in header_map.items():
                if not header:
                    continue
                parsed_row[header] = str(row_values_by_index.get(index, "")).strip()

            row_number = int(row.attrib.get("r", "0") or "0")
            if row_number <= 0:
                row_number = header_row_index + offset
            parsed_rows.append(ParsedRow(row_number=row_number, values=parsed_row))

        return parsed_rows


def read_xlsx_row_cells(file_path: Path, max_rows: int = 0) -> list[dict[int, str]]:
    with ZipFile(file_path) as zip_file:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in zip_file.namelist():
            shared_root = ET.fromstring(zip_file.read("xl/sharedStrings.xml"))
            for item in shared_root.findall("main:si", NS):
                shared_strings.append(_itertext(item))

        workbook_root = ET.fromstring(zip_file.read("xl/workbook.xml"))
        rels_root = ET.fromstring(zip_file.read("xl/_rels/workbook.xml.rels"))
        rel_by_id = {
            rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_root.findall("pkgrel:Relationship", NS)
        }

        sheets = workbook_root.findall("main:sheets/main:sheet", NS)
        if not sheets:
            return []
        first_sheet = sheets[0]

        rel_id = first_sheet.attrib.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", ""
        )
        sheet_target = rel_by_id.get(rel_id, "")
        if not sheet_target:
            return []
        if not sheet_target.startswith("worksheets/"):
            sheet_target = "worksheets/" + Path(sheet_target).name

        sheet_root = ET.fromstring(zip_file.read("xl/" + sheet_target))
        rows = sheet_root.findall("main:sheetData/main:row", NS)
        if not rows:
            return []

        parsed_rows: list[dict[int, str]] = []
        for row in rows:
            parsed_row: dict[int, str] = {}
            for cell in row.findall("main:c", NS):
                index = _col_index(cell.attrib.get("r", ""))
                if index is None:
                    continue
                value = _cell_value(cell, shared_strings).strip()
                if value:
                    parsed_row[index] = value
            parsed_rows.append(parsed_row)
            if max_rows > 0 and len(parsed_rows) >= max_rows:
                break
        return parsed_rows


def _decode_tabular_text(raw_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def _detect_csv_dialect(sample_text: str) -> csv.Dialect | csv.excel:
    if sample_text.strip():
        try:
            return csv.Sniffer().sniff(sample_text, delimiters=";,\t")
        except csv.Error:
            pass

    semicolons = sample_text.count(";")
    commas = sample_text.count(",")
    tabs = sample_text.count("\t")
    delimiter = ";"
    if commas > semicolons and commas >= tabs:
        delimiter = ","
    elif tabs > semicolons and tabs > commas:
        delimiter = "\t"

    class _FallbackDialect(csv.excel):
        pass

    _FallbackDialect.delimiter = delimiter
    return _FallbackDialect


def read_csv_rows(file_path: Path, header_row_index: int = 1) -> list[ParsedRow]:
    if header_row_index < 1:
        raise ValueError("header_row_index must be >= 1")

    raw_bytes = file_path.read_bytes()
    text = _decode_tabular_text(raw_bytes)
    lines = text.splitlines()
    if not lines:
        return []
    if header_row_index > len(lines):
        raise ValueError(
            f"header_row_index={header_row_index} is out of range for sheet with {len(lines)} rows"
        )

    sample_text = "\n".join(lines[: min(len(lines), 10)])
    dialect = _detect_csv_dialect(sample_text)
    reader = csv.reader(lines, dialect=dialect)
    rows = list(reader)
    if not rows:
        return []
    if header_row_index > len(rows):
        raise ValueError(
            f"header_row_index={header_row_index} is out of range for sheet with {len(rows)} rows"
        )

    header_values = [str(item or "").strip() for item in rows[header_row_index - 1]]
    parsed_rows: list[ParsedRow] = []
    for row_number, raw_row in enumerate(rows[header_row_index:], start=header_row_index + 1):
        parsed_row: dict[str, str] = {}
        for index, header in enumerate(header_values):
            if not header:
                continue
            parsed_row[header] = str(raw_row[index] if index < len(raw_row) else "").strip()
        parsed_rows.append(ParsedRow(row_number=row_number, values=parsed_row))

    return parsed_rows


def read_csv_row_cells(file_path: Path, max_rows: int = 0) -> list[dict[int, str]]:
    raw_bytes = file_path.read_bytes()
    text = _decode_tabular_text(raw_bytes)
    lines = text.splitlines()
    if not lines:
        return []

    sample_text = "\n".join(lines[: min(len(lines), 10)])
    dialect = _detect_csv_dialect(sample_text)
    reader = csv.reader(lines, dialect=dialect)

    parsed_rows: list[dict[int, str]] = []
    for raw_row in reader:
        parsed_rows.append(
            {
                index: str(value).strip()
                for index, value in enumerate(raw_row)
                if str(value).strip()
            }
        )
        if max_rows > 0 and len(parsed_rows) >= max_rows:
            break
    return parsed_rows


def read_tabular_row_cells(file_path: Path, max_rows: int = 0) -> list[dict[int, str]]:
    suffix = file_path.suffix.lower()
    if suffix == ".xlsx":
        return read_xlsx_row_cells(file_path, max_rows=max_rows)
    if suffix == ".csv":
        return read_csv_row_cells(file_path, max_rows=max_rows)
    raise ValueError(f"Unsupported tabular format for raw cell reading: {file_path.name}")


def composition_section(section: str, family: str) -> str:
    s = normalize_token(section)
    f = normalize_token(family)
    if s and f:
        return f"{s}:{f}"
    if s:
        return s
    if f:
        return f"family:{f}"
    return "general"


def resolve_species_local_and_code(
    source_text: str,
    contains_rules: list[dict[str, str]],
    fallback_to_source: bool = True,
) -> tuple[str, str | None]:
    raw = str(source_text or "").strip()
    if not raw:
        return ("", None)
    normalized_raw = normalize_token(raw)

    for rule in contains_rules:
        contains_text = str(rule.get("contains", "")).strip()
        if not contains_text:
            continue
        normalized_contains = normalize_token(contains_text)
        if normalized_contains and normalized_contains in normalized_raw:
            mapped_value = str(
                rule.get("value")
                or rule.get("local")
                or rule.get("label")
                or contains_text
            ).strip()
            return (mapped_value or raw, None)

    return (raw, None) if fallback_to_source else ("", None)


def resolve_species_local(
    source_text: str,
    contains_rules: list[dict[str, str]],
    fallback_to_source: bool = True,
) -> str:
    return resolve_species_local_and_code(
        source_text=source_text,
        contains_rules=contains_rules,
        fallback_to_source=fallback_to_source,
    )[0]


def _iso_utc(dt: datetime) -> str:
    with_tz = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    as_utc = with_tz.astimezone(timezone.utc).replace(microsecond=0)
    return as_utc.isoformat().replace("+00:00", "Z")


def _parse_excel_serial(date_text: str) -> datetime | None:
    try:
        serial = float(date_text)
    except ValueError:
        return None
    if serial <= 0:
        return None
    base = datetime(1899, 12, 30, tzinfo=timezone.utc)
    return base + timedelta(days=serial)


def _parse_time(time_text: str) -> tuple[int, int, int] | None:
    text = str(time_text or "").strip()
    if not text:
        return None
    match = TIME_RE.match(text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    second = int(match.group(3) or "0")
    if hour > 23 or minute > 59 or second > 59:
        return None
    return (hour, minute, second)


def _parse_iso_or_common(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    known_formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
    )
    for fmt in known_formats:
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _parse_spanish_long_date(date_text: str, time_text: str) -> datetime | None:
    match = SPANISH_LONG_DATE_RE.match(str(date_text or ""))
    if not match:
        return None
    day = int(match.group(1))
    month_name = normalize_token(match.group(2))
    year = int(match.group(3))
    month = SPANISH_MONTHS.get(month_name)
    if not month:
        return None

    hour = 0
    minute = 0
    second = 0
    parsed_time = _parse_time(time_text)
    if parsed_time:
        hour, minute, second = parsed_time
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def parse_fhir_datetime(date_raw: str, time_raw: str = "") -> str:
    date_text = str(date_raw or "").strip()
    time_text = str(time_raw or "").strip()
    if not date_text and not time_text:
        return _iso_utc(datetime.now(timezone.utc))

    excel_dt = _parse_excel_serial(date_text)
    if excel_dt is not None:
        parsed_time = _parse_time(time_text)
        if parsed_time:
            excel_dt = excel_dt.replace(
                hour=parsed_time[0],
                minute=parsed_time[1],
                second=parsed_time[2],
                microsecond=0,
            )
        return _iso_utc(excel_dt)

    spanish_dt = _parse_spanish_long_date(date_text, time_text)
    if spanish_dt is not None:
        return _iso_utc(spanish_dt)

    if date_text and time_text:
        combined = f"{date_text} {time_text}".strip()
        parsed = _parse_iso_or_common(combined)
        if parsed is not None:
            return _iso_utc(parsed)

    parsed_date_only = _parse_iso_or_common(date_text)
    if parsed_date_only is not None:
        parsed_time = _parse_time(time_text)
        if parsed_time:
            parsed_date_only = parsed_date_only.replace(
                hour=parsed_time[0],
                minute=parsed_time[1],
                second=parsed_time[2],
                microsecond=0,
            )
        return _iso_utc(parsed_date_only)

    return _iso_utc(datetime.now(timezone.utc))
