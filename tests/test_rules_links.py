# Flow contract: DataConv exposes one repository-owned, locally resolvable rules graph without importing private operational authority.
from pathlib import Path
import re


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def relative_targets(markdown: str) -> list[str]:
    targets = re.findall(r"\[[^\]]+\]\(([^)]+)\)", markdown)
    return [
        target.split("#", 1)[0]
        for target in targets
        if target and not re.match(r"^(?:https?:|mailto:|#)", target)
    ]


def test_repository_rules_graph_is_complete_and_locally_resolvable() -> None:
    agents_path = REPOSITORY_ROOT / "AGENTS.md"
    index_path = REPOSITORY_ROOT / "docs" / "RULES_INDEX.md"
    agents = agents_path.read_text(encoding="utf-8")
    index = index_path.read_text(encoding="utf-8")

    assert "docs/RULES_INDEX.md" in agents
    assert "index provider" in agents.lower()
    assert "not a clinic" in agents.lower()
    assert "../.codex/skills/preserve-fhir-flat-claim-boundaries/SKILL.md" in index
    assert "../README.md" in index
    assert "../CHANGELOG.md" in index
    assert "connectech-operations-private" not in f"{agents}\n{index}"

    for path, markdown in ((agents_path, agents), (index_path, index)):
        for target in relative_targets(markdown):
            assert (path.parent / target).resolve().exists(), f"broken rule link: {path} -> {target}"
