"""Which of a node's ports the plan connects.

Owner, 2026-11-20 (rasl-2lg): a node whose directions follow its wiring (an sACN
universe sends when its input is wired and receives when an output is) reads this
from ``NodeContext.wiring`` and, for its rate, from ``@pull_rate(..., wiring=True)``.
It comes from the plan, never from port state, so it is the same at load, at start
and after a plan update.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True, slots=True)
class Wiring:
    """The names of a node's ports that have at least one edge in the plan.

    Attributes:
        inputs: Input ports with an incoming edge (a back edge counts).
        outputs: Output ports with an outgoing edge (a back edge counts).
    """

    inputs: FrozenSet[str] = frozenset()
    outputs: FrozenSet[str] = frozenset()
