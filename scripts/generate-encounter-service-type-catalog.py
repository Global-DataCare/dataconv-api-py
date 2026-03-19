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

SERVICE_TYPE_VALUE_SET = "http://hl7.org/fhir/ValueSet/service-type"
SERVICE_TYPE_SYSTEM = "http://terminology.hl7.org/CodeSystem/service-type"


@dataclass(frozen=True)
class CodeRow:
    code: str
    display: str
    definition: str


class _TableParser(HTMLParser):
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


def _strip_anchor_prefix(cell_text: str) -> str:
    text = str(cell_text or "").strip()
    if not text:
        return ""
    parts = text.split()
    if parts and parts[0].isdigit():
        return parts[0]
    return text


def _parse_rows(html_path: Path) -> list[CodeRow]:
    parser = _TableParser()
    parser.feed(html_path.read_text(encoding="utf-8", errors="ignore"))

    rows: list[CodeRow] = []
    seen: set[str] = set()
    for raw in parser.rows:
        if len(raw) < 3:
            continue
        code = _strip_anchor_prefix(raw[0])
        if not code.isdigit():
            continue
        if code in seen:
            continue
        display = str(raw[1]).strip()
        definition = str(raw[2]).strip()
        if not display:
            continue
        seen.add(code)
        rows.append(CodeRow(code=code, display=display, definition=definition))
    return rows


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Generate FHIR R4 Encounter.serviceType catalog JSON from local HL7 HTML.")
    parser.add_argument(
        "--input-html",
        default=str(repo_root.parent / "Encounter-Valueset-service-type - FHIR v4.0.1.html"),
        help="Path to downloaded HL7 valueset-service-type HTML file.",
    )
    parser.add_argument(
        "--output-json",
        default=str(repo_root / "configs" / "fhir-encounter-service-type.r4.json"),
        help="Output JSON file path.",
    )
    args = parser.parse_args()

    input_html = Path(args.input_html).expanduser().resolve()
    output_json = Path(args.output_json).expanduser().resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)

    if not input_html.exists():
        raise FileNotFoundError(f"Input HTML not found: {input_html}")

    rows = _parse_rows(input_html)
    payload = {
        "system": SERVICE_TYPE_SYSTEM,
        "valueSet": SERVICE_TYPE_VALUE_SET,
        "profile": "r4-encounter-service-type",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceFile": str(input_html),
        "codes": {
            row.code: {
                "display": row.display,
                "definition": row.definition,
            }
            for row in rows
        },
    }

    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"codes: {len(rows)}")
    print(f"output: {output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
