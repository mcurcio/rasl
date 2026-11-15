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

