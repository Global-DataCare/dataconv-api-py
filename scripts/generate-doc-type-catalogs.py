#!/usr/bin/env python3
# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
import argparse
import json
import re


FHIR_DOC_TYPE_VALUE_SET = "http://hl7.org/fhir/ValueSet/c80-doc-typecodes"
LOINC_SYSTEM = "http://loinc.org"

# Human-oriented terms intentionally excluded from the veterinary base catalog.
HUMAN_EXTENSION_KEYWORDS = [
    "pediatric",
    "paediatric",
    "child",
    "infant",
    "neonat",
    "adolescent",
    "school record",
    "newborn",
    "maternal",
    "pregnan",
    "obstet",
    "labor and delivery",
    "nursing mothers",
    "breastfeeding",
    "menopause",
]

# US profile extension requested from display text.
US_EXTENSION_PATTERNS = [
    r"\bUS\b",
    r"\bFDA\b",
]


@dataclass(frozen=True)
class CodeRow:
    code: str
    display: str


class _DocTypeTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_row = False
        self._in_cell = False
        self._current_cell: list[str] = []
        self._current_row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag == "tr":
            self._in_row = True
            self._current_row = []
            return
        if tag == "td" and self._in_row:
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag == "td" and self._in_cell:
            text = " ".join("".join(self._current_cell).split())
            self._current_row.append(text)
            self._in_cell = False
            return
        if tag == "tr" and self._in_row:
            if self._current_row:
                self.rows.append(self._current_row)
            self._in_row = False

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._in_cell:
            self._current_cell.append(data)


def _parse_rows(html_path: Path) -> list[CodeRow]:
    parser = _DocTypeTableParser()
    parser.feed(html_path.read_text(encoding="utf-8", errors="ignore"))

    code_pattern = re.compile(r"\d{1,7}-\d")
    seen: set[str] = set()
    rows: list[CodeRow] = []
    for raw in parser.rows:
        if len(raw) < 2:
            continue
        code = raw[0].strip()
        display = raw[1].strip()
        if not code_pattern.fullmatch(code):
            continue
        if not display:
            continue
        if code in seen:
            continue
        seen.add(code)
        rows.append(CodeRow(code=code, display=display))
    return rows


def _is_human_extension(display: str) -> bool:
    lowered = display.lower()
    return any(keyword in lowered for keyword in HUMAN_EXTENSION_KEYWORDS)


def _is_us_extension(display: str) -> bool:
    return any(re.search(pattern, display, flags=re.IGNORECASE) for pattern in US_EXTENSION_PATTERNS)


def _catalog_payload(
    *,
    profile: str,
    extends: str | None,
    source_path: Path,
    rows: list[CodeRow],
    base_count: int,
    human_extension_count: int,
    us_extension_count: int,
) -> dict:
    return {
        "system": LOINC_SYSTEM,
        "valueSet": FHIR_DOC_TYPE_VALUE_SET,
        "profile": profile,
        "extends": extends or "",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceFile": str(source_path),
        "filters": {
            "humanExtensionKeywords": HUMAN_EXTENSION_KEYWORDS,
            "usExtensionDisplayPatterns": US_EXTENSION_PATTERNS,
        },
        "counts": {
            "sourceTotal": base_count + human_extension_count + us_extension_count,
            "humanExtensionTotal": human_extension_count,
            "usExtensionTotal": us_extension_count,
            "profileTotal": len(rows),
        },
        "codes": {row.code: row.display for row in rows},
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Generate DocumentReference.type catalogs from HL7 R4 c80-doc-typecodes HTML.")
    parser.add_argument(
        "--input-html",
        default=str(repo_root.parent / "hl7.org_fhir_R4_valueset-c80-doc-typecodes.html"),
        help="Path to downloaded HL7 valueset-c80-doc-typecodes HTML file.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(repo_root / "configs"),
        help="Directory where generated JSON files will be written.",
    )
    args = parser.parse_args()

    input_html = Path(args.input_html).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_html.exists():
        raise FileNotFoundError(f"Input HTML not found: {input_html}")

    source_rows = _parse_rows(input_html)
    human_extension_codes = {row.code for row in source_rows if _is_human_extension(row.display)}
    us_extension_codes = {row.code for row in source_rows if _is_us_extension(row.display)}

    vet_rows = [row for row in source_rows if row.code not in human_extension_codes and row.code not in us_extension_codes]
    human_rows = [row for row in source_rows if row.code in {r.code for r in vet_rows} or row.code in human_extension_codes]
    us_rows = [row for row in source_rows if row.code in {r.code for r in human_rows} or row.code in us_extension_codes]

    payloads = {
        "fhir-documentreference-typecodes.international.veterinary.json": _catalog_payload(
            profile="international-veterinary",
            extends=None,
            source_path=input_html,
            rows=vet_rows,
            base_count=len(vet_rows),
            human_extension_count=len(human_extension_codes),
            us_extension_count=len(us_extension_codes - human_extension_codes),
        ),
        "fhir-documentreference-typecodes.international.human.json": _catalog_payload(
            profile="international-human",
            extends="international-veterinary",
            source_path=input_html,
            rows=human_rows,
            base_count=len(vet_rows),
            human_extension_count=len(human_extension_codes),
            us_extension_count=len(us_extension_codes - human_extension_codes),
        ),
        "fhir-documentreference-typecodes.us.human.json": _catalog_payload(
            profile="us-human",
            extends="international-human",
            source_path=input_html,
            rows=us_rows,
            base_count=len(vet_rows),
            human_extension_count=len(human_extension_codes),
            us_extension_count=len(us_extension_codes - human_extension_codes),
        ),
    }

    for name, payload in payloads.items():
        (output_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"source rows: {len(source_rows)}")
    for name, payload in payloads.items():
        print(f"{name}: {payload['counts']['profileTotal']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
