"""When things are due: which nodes drive the rates, and each one's due times."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set, Tuple

from rasl.graph import ExecutionPlan


def pull_rate_of(node_id: str, node: object) -> Optional[float]:
    """The rate in Hz a node's pull() declares with @pull_rate, or None if it declares none.

    Raises:
        ValueError: If the declared rate is not a positive, finite number.
    """
    hz = getattr(getattr(node, "pull", None), "_pull_rate_hz", None)
    if hz is None:
        return None
    if callable(hz):
        hz = hz(node)
    try:
        hz = float(hz)
    except (TypeError, ValueError):
        raise ValueError(f"Node '{node_id}' declares a pull rate of {hz!r}; it must be a number") from None
    if not math.isfinite(hz) or hz <= 0.0:
        raise ValueError(
            f"Node '{node_id}' declares a pull rate of {hz} Hz; it must be positive and finite"
        )
    return hz


def find_rate_drivers(plan: ExecutionPlan) -> Dict[str, float]:
    """The nodes whose pull() declares a rate with @pull_rate, and that rate in Hz.

    Raises:
        ValueError: If a declared rate is not a positive, finite number.
    """
    drivers: Dict[str, float] = {}
    for node_id, node in plan.nodes.items():
        hz = pull_rate_of(node_id, node)
        if hz is not None:
            drivers[node_id] = hz
    return drivers


def find_undriven(plan: ExecutionPlan, drivers: Optional[Dict[str, float]] = None) -> List[str]:
    """The nodes nothing pulls: not a rate driver, and not upstream of one.

    Such a node is loaded and started but its pull() never runs. With no rate
    driver at all, that is every node.

    Args:
        plan: The compiled plan.
        drivers: The plan's rate drivers, if already worked out.

    Returns:
        Node ids, in the plan's order.
    """
    if drivers is None:
        drivers = find_rate_drivers(plan)
    upstream: Dict[str, List[str]] = defaultdict(list)
    for source, edges in plan.adjacency.items():
        for edge in edges:
            upstream[edge.target].append(source)
    driven: Set[str] = set()
    pending = list(drivers)
    while pending:
        node_id = pending.pop()
        if node_id not in driven:
            driven.add(node_id)
            pending.extend(upstream[node_id])
    return [node_id for node_id in plan.topological_order if node_id not in driven]


class DueTimes:
    """When each rate driver is next due.

    A driver with rate ``hz`` is due at ``t0 + n / hz`` for n = 0, 1, 2, ...
    Every driver counts from the same ``t0``, so drivers whose periods meet
    (30 Hz and 20 Hz, every 100 ms) are due at the same instants and share a
    tick. Any positive rate keeps its own period; nothing is rounded to a
    common cycle.
    """

    MERGE_SECONDS = 1e-6
    """Drivers due within this much of the earliest one share its tick."""

    def __init__(self, rates: Dict[str, float], t0: float, now: Optional[float] = None) -> None:
        """Start counting.

        Args:
            rates: Rate in Hz of each driver, by node id.
            t0: The instant every driver counts from.
            now: None to start each driver at ``t0``. Otherwise each driver
                starts at its first due time not before ``now``, so a driver
                that kept its rate across a plan update keeps its timing.
        """
        self._rates = dict(rates)
        self._t0 = t0
        self._n: Dict[str, int] = {
            driver: 0 if now is None else self._first_at_or_after(driver, now)
            for driver in self._rates
        }

    def _first_at_or_after(self, driver: str, now: float) -> int:
        return max(0, math.ceil((now - self._t0) * self._rates[driver] - 1e-9))

    def due(self, driver: str) -> float:
        """The next due time of one driver."""
        return self._t0 + self._n[driver] / self._rates[driver]

    def next(self) -> Tuple[float, Tuple[str, ...]]:
        """The next tick: its time, and the drivers due at it."""
        dues = {driver: self.due(driver) for driver in self._rates}
        earliest = min(dues.values())
        return earliest, tuple(
            driver for driver, due in dues.items() if due - earliest < self.MERGE_SECONDS
        )

    def advance(self, ran: Iterable[str], now: float) -> Dict[str, int]:
        """Move on after a tick.

        Each driver in ``ran`` moves to its next due time. Then any driver that
        is more than one of its periods late jumps to its first due time not
        before ``now``; the due times it passes over are dropped, not replayed.
        A driver less than a period late keeps its due time and runs late.

        Args:
            ran: The drivers pulled in the tick just finished.
            now: The current time.

        Returns:
            How many due times each driver dropped, for those that dropped any.
        """
        for driver in ran:
            self._n[driver] += 1
        dropped: Dict[str, int] = {}
        for driver, hz in self._rates.items():
            if now - self.due(driver) > 1.0 / hz:
                n = self._first_at_or_after(driver, now)
                dropped[driver] = n - self._n[driver]
                self._n[driver] = n
        return dropped
