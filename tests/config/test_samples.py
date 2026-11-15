"""The sample configs at the repository root keep loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from rasl.config import load_config

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", ["virtual.conf", "hyperhdr.conf"])
def test_sample_config_loads(name: str) -> None:
    plan = load_config(ROOT / name)
    assert plan.nodes


def test_family_room_gets_as_far_as_its_known_connect_error() -> None:
    """family_room.conf does not load (rasl-pd0.7: SacnSource has no default
    output port). Everything before that error must still be accepted, so a
    change that breaks another part of it shows up here."""
    from rasl.config import ConfigError

    with pytest.raises(ConfigError, match="hyperhdr_color.*No default port"):
        load_config(ROOT / "family_room.conf")
