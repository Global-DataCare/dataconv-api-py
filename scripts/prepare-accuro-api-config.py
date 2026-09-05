#!/usr/bin/env python3
# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adapter_ingestion.accuro_workbook import prepare_accuro_workbook


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add API-CONFIG mappings and stable ResearchSubject UUIDs to the Accuro workbook."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--split-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    report = prepare_accuro_workbook(args.source, args.output, split_dir=args.split_dir)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
