"""pull_rate_of: a rate may be None (this instance drives nothing) or depend on wiring."""

from __future__ import annotations

import math

import pytest

from rasl.graph.node import BaseNode, TickContext, Wiring, pull_rate
from rasl.runtime import pull_rate_of


class _Fixed(BaseNode):
    @pull_rate(lambda self: self.rate)
    async def pull(self, tick: TickContext) -> None:
        """Do nothing."""

    def __init__(self, rate: object) -> None:
        self.rate = rate


class _Wired(BaseNode):
    @pull_rate(lambda self, wiring: 40.0 if "dmx" in wiring.inputs else None, wiring=True)
    async def pull(self, tick: TickContext) -> None:
        """Do nothing."""

    def __init__(self) -> None:
        pass


def test_a_rate_callable_returning_none_means_the_node_drives_nothing() -> None:
    assert pull_rate_of("n", _Fixed(None)) is None


@pytest.mark.parametrize("bad", ["x", 0, -1.0, math.inf, math.nan])
def test_a_rate_that_is_not_none_must_be_a_positive_finite_number(bad: object) -> None:
    with pytest.raises(ValueError):
        pull_rate_of("n", _Fixed(bad))


def test_a_wiring_rate_sees_the_nodes_wiring() -> None:
    node = _Wired()
    assert pull_rate_of("n", node, Wiring(inputs=frozenset({"dmx"}))) == 40.0
    assert pull_rate_of("n", node, Wiring(outputs=frozenset({"dmx"}))) is None


def test_a_wiring_rate_without_wiring_is_an_error() -> None:
    with pytest.raises(ValueError, match="wiring"):
        pull_rate_of("n", _Wired())


def test_a_node_without_a_declared_rate_has_none() -> None:
    class _Plain(BaseNode):
        def __init__(self) -> None:
            pass

        async def pull(self, tick: TickContext) -> None:
            """Do nothing."""

    assert pull_rate_of("n", _Plain()) is None
