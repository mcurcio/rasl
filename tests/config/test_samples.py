"""The sample configs at the repository root keep loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from rasl.config import load_config

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", ["virtual.conf", "hyperhdr.conf", "family_room.conf"])
def test_sample_config_loads(name: str) -> None:
    plan = load_config(ROOT / name)
    assert plan.nodes



def _docstring_examples() -> list[tuple[str, str]]:
    """Every `graph { ... }` example in the source's docstrings, by file."""
    import re
    import textwrap

    examples = []
    for path in sorted((ROOT / "src" / "rasl").rglob("*.py")):
        text = path.read_text()
        for match in re.finditer(r"^([ \t]*)graph \{\n.*?^\1\}", text, re.S | re.M):
            examples.append((str(path.relative_to(ROOT)), textwrap.dedent(match.group(0))))
    return examples


@pytest.mark.parametrize(("where", "example"), _docstring_examples(), ids=lambda v: v if v.endswith(".py") else "")
def test_docstring_examples_load(where: str, example: str) -> None:
    from rasl.config.build import parse_config

    assert parse_config(example).nodes, where
