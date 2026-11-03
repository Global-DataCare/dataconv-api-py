# Flow contract: the immutable DataConv image installs the released Python claim catalog required by its exact runtime dependency.

import tomllib
from pathlib import Path


RELEASE_WHEEL = (
    "gdc-data-utils-py @ "
    "https://github.com/Global-DataCare/gdc-data-utils-py/releases/download/"
    "v0.1.1/gdc_data_utils_py-0.1.1-py3-none-any.whl"
    "#sha256=d1e51f2b30e5f0edfa4c19eeeae769a3bb6cd67ff45b6499a7b193effc39c66e"
)


def test_package_metadata_uses_the_immutable_released_claim_catalog() -> None:
    with Path("pyproject.toml").open("rb") as stream:
        dependencies = tomllib.load(stream)["project"]["dependencies"]

    assert dependencies == [RELEASE_WHEEL]


def test_container_pins_released_gdc_data_utils_wheel() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "releases/download/v0.1.1/gdc_data_utils_py-0.1.1-py3-none-any.whl" in dockerfile
    assert "d1e51f2b30e5f0edfa4c19eeeae769a3bb6cd67ff45b6499a7b193effc39c66e" in dockerfile
    assert "pip install /tmp/gdc_data_utils_py-0.1.1-py3-none-any.whl" in dockerfile
