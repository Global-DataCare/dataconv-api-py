#!/usr/bin/env python3
# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adapter_ingestion.research_search_workbooks import generate_research_search_workbooks


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate anonymous veterinary and human research-search Excel fixtures."
    )
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    generated = generate_research_search_workbooks(args.output_dir)
    print(json.dumps({key: str(value) for key, value in generated.items()}, indent=2))


if __name__ == "__main__":
    main()
