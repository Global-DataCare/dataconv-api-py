# Flow contract: the immutable DataConv image installs the released Python claim catalog required by its exact runtime dependency.

from pathlib import Path


def test_container_pins_released_gdc_data_utils_wheel() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "releases/download/v0.1.1/gdc_data_utils_py-0.1.1-py3-none-any.whl" in dockerfile
    assert "d1e51f2b30e5f0edfa4c19eeeae769a3bb6cd67ff45b6499a7b193effc39c66e" in dockerfile
    assert "pip install /tmp/gdc_data_utils_py-0.1.1-py3-none-any.whl" in dockerfile
