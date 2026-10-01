# Flow contract: shared DataConv source, scripts, tests and documentation remain product-neutral and do not identify a promoter as the product owner.

from pathlib import Path
import subprocess


def test_versionable_repository_paths_and_text_are_product_neutral() -> None:
    repository = Path(__file__).resolve().parents[1]
    forbidden = "acc" + "uro"
    versionable = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    branded_paths = [path for path in versionable if forbidden in path.casefold()]
    branded_text = []
    for relative_path in versionable:
        path = repository / relative_path
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError):
            continue
        if forbidden in content.casefold():
            branded_text.append(relative_path)

    assert branded_paths == []
    assert branded_text == []
