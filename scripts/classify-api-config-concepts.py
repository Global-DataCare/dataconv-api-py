#!/usr/bin/env python3
"""Write a private row-level resource-classification review queue."""

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

from adapter_ingestion.api_config_concept_review import classify_workbook


FIELDS = (
    "sheet",
    "row_number",
    "resource_type",
    "source_text",
    "confidence",
    "basis",
    "section",
    "family",
    "subfamily",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args()
    result = classify_workbook(args.workbook)
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    records = [{field: getattr(item, field) for field in FIELDS} for item in result.rows]
    with (args.evidence_dir / "resource-candidates.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)
    summary = {
        "workbook": str(args.workbook),
        "candidateRows": len(records),
        "countsByResourceType": result.counts_by_resource_type,
        "countsBySheet": result.counts_by_sheet,
    }
    (args.evidence_dir / "resource-candidates-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown = [
        "# API-CONFIG source concept classification",
        "",
        "Review-only candidates; no inferred code or resource is authoritative until confirmed.",
        "",
        f"Candidate rows: **{len(records)}**",
        "",
        "## By resource type",
        "",
        "| Resource type | Candidates |",
        "|---|---:|",
        *(f"| {resource_type} | {count} |" for resource_type, count in result.counts_by_resource_type.items()),
        "",
        "The row-level CSV preserves the source sheet, row, hierarchy, original text, confidence and basis.",
    ]
    (args.evidence_dir / "resource-candidates-README.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
