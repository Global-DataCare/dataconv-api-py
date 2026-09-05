#!/usr/bin/env python3
"""Create a governed copy of an agnostic DataConv mapping workbook."""

from __future__ import annotations

import argparse
from pathlib import Path

from adapter_ingestion.base_config_contract import reconcile_base_config_workbook


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    reconcile_base_config_workbook(args.source, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
