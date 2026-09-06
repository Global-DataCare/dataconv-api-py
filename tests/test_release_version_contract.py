# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
import sys
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapter_ingestion import __version__


# Flow contract: the immutable image and its public OpenAPI document must report
# the exact release version declared by the Python package manifest.
class ReleaseVersionContractTests(unittest.TestCase):
    def test_runtime_version_matches_pyproject_release(self) -> None:
        with (ROOT / "pyproject.toml").open("rb") as stream:
            project_version = tomllib.load(stream)["project"]["version"]

        self.assertEqual(__version__, project_version)


if __name__ == "__main__":
    unittest.main()
