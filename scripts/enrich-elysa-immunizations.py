#!/usr/bin/env python3
"""Create a reviewable ATC/ATCvet-enriched copy of the Elysa workbook."""

# Copyright ConnectHealth.info (Connecting Solution & Applications Ltd.)
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapter_ingestion.elysa_immunization_coding import enrich_workbook


CSV_FIELDS = (
    "sheet",
    "source_column",
    "original_text",
    "codes",
    "displays",
    "texts_es",
    "species_codes",
    "species_display",
    "confidence",
    "basis",
    "matched_rows",
    "row_numbers",
)


def _record(item: object) -> dict[str, object]:
    return {
        "sheet": item.sheet,
        "source_column": item.source_column,
        "original_text": item.original_text,
        "codes": item.codes,
        "displays": item.displays,
        "texts_es": item.texts_es,
        "species_codes": item.species_codes,
        "species_display": item.species_display,
        "confidence": item.confidence,
        "basis": item.basis,
        "matched_rows": item.matched_rows,
        "row_numbers": ",".join(str(row) for row in item.row_numbers),
    }


def _write_evidence(summary: object, evidence_dir: Path, workbook_path: Path) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    records = [_record(item) for item in summary.items]
    csv_path = evidence_dir / "immunizations-detected.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(records)

    json_path = evidence_dir / "immunizations-detected.json"
    json_path.write_text(
        json.dumps(
            {
                "workbook": str(workbook_path),
                "matchedRows": summary.matched_rows,
                "matchedRowsBySheet": summary.matched_rows_by_sheet,
                "items": records,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    markdown = [
        "# Elysa immunization coding evidence",
        "",
        f"Derived workbook: `{workbook_path}`",
        "",
        f"Matched source rows: **{summary.matched_rows}**",
        "",
        "## Rows by sheet",
        "",
        "| Sheet | Matched rows |",
        "|---|---:|",
    ]
    markdown.extend(
        f"| {sheet} | {count} |" for sheet, count in summary.matched_rows_by_sheet.items()
    )
    markdown.extend(
        [
            "",
            "## Detected source texts and inferred candidates",
            "",
            "The codes are review candidates inferred from the source text, not confirmed product-authorisation identifiers.",
            "",
        ]
    )
    for record in records:
        rows = str(record["row_numbers"]).split(",")
        row_label = ",".join(rows) if len(rows) <= 20 else f"{','.join(rows[:10])},...,{','.join(rows[-3:])} ({len(rows)} rows)"
        original_text = " ".join(str(record["original_text"]).split())
        markdown.extend(
            [
                f"### {record['sheet']} — rows {row_label}",
                "",
                f"- Original: {original_text}",
                f"- Codes: `{record['codes']}`",
                f"- International display: {record['displays']}",
                f"- Spanish text: {record['texts_es']}",
                f"- Inferred species: `{record['species_codes']}` ({record['species_display']})",
                f"- Confidence: {record['confidence']}",
                f"- Basis: {record['basis']}",
                "",
            ]
        )
    (evidence_dir / "README.md").write_text("\n".join(markdown), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args()

    summary = enrich_workbook(args.source, args.target)
    _write_evidence(summary, args.evidence_dir, args.target)
    print(json.dumps({"matchedRows": summary.matched_rows, "bySheet": summary.matched_rows_by_sheet}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
