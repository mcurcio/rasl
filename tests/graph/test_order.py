"""toposort_with_cycles: the order of a graph that holds a cycle."""

from __future__ import annotations

import pytest

from rasl.graph.edge import Edge
from rasl.graph.order import toposort_with_cycles


def _edge(source: str, target: str) -> Edge:
    return Edge(source=source, source_port="out", target=target, target_port="in")


def test_an_acyclic_graph_is_ordered_sources_first() -> None:
    order, cycles = toposort_with_cycles(["c", "b", "a"], [_edge("a", "b"), _edge("b", "c")])
    assert order == ("a", "b", "c")
    assert cycles == []


@pytest.mark.parametrize(
    ("nodes", "expected"),
    [
        (["zeta", "alpha", "mid"], ("zeta", "alpha", "mid")),
        (["alpha", "mid", "zeta"], ("alpha", "mid", "zeta")),
        (["mid", "zeta", "alpha"], ("mid", "zeta", "alpha")),
    ],
)
def test_a_cycle_is_broken_at_the_first_node_given(nodes: list[str], expected: tuple[str, ...]) -> None:
    """It was broken at whichever node a set of strings yielded first, which differs between
    processes (rasl-pd0.16)."""
    ring = [_edge("zeta", "alpha"), _edge("alpha", "mid"), _edge("mid", "zeta")]
    order, cycles = toposort_with_cycles(nodes, ring)
    assert order == expected
    assert len(cycles) == 1


def test_nodes_behind_a_cycle_follow_it() -> None:
    edges = [_edge("a", "b"), _edge("b", "a"), _edge("b", "sink")]
    order, _cycles = toposort_with_cycles(["sink", "b", "a"], edges)
    assert order == ("b", "a", "sink")
