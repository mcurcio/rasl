"""Garbage collection between ticks.

Python's cyclic collector stops the interpreter for as long as it runs, and it runs when an
allocation count is reached, which is in the middle of a tick as often as not. While ticks
run, the collector here turns the automatic one off and collects in the gaps between ticks
instead, when a gap is long enough.
"""

from __future__ import annotations

import gc
import time
from collections.abc import Callable

_OLDEST = 2

_PASSES_PER_OLDER = 10
"""Passes over one generation before the next older one is collected (CPython's own ratio)."""

_FIRST_ESTIMATE_S = 0.002
"""Assumed time of a pass that has not been measured yet."""

_MARGIN_S = 0.001

_OVERDUE_S = 10.0
"""A pass that no gap has been long enough for in this long is run in the next gap anyway."""


class IdleCollector:
    """Runs the cyclic garbage collector in the gaps between ticks.

    ``begin()`` freezes every object alive at that moment (the imported modules, the node
    classes, the first plan): later passes do not look at them, which takes a full pass in a
    loaded process from about 50 ms to well under one. It collects the two young generations
    first and not the oldest, because a full pass there is the 50 ms stall this class exists
    to avoid. From then on ``collect_if_time()`` runs one pass per gap, of the youngest
    generation nine times in ten, of the middle one after ten of those, and of all three after
    ten of the middle one, so an object that outlives one pass is still looked at again. A
    pass runs when the gap is at least twice what the last pass of that generation took, or
    when none has run for 10 s.

    Frozen objects are still freed when their reference count reaches zero. A reference cycle
    made only of objects frozen at ``begin()`` is not freed until ``end()``: that is the first
    plan's cycles after a reload, and whatever garbage the oldest generation held at the start.

    ``suspend()`` hands collection back to Python while no tick is
    due, without undoing the freeze.

    Attributes:
        active: True between ``begin()`` and ``end()``.
        suspended: True while active and automatic collection is on (``suspend()``).
    """

    def __init__(
        self,
        *,
        collect: Callable[[int], object] = gc.collect,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """
        Args:
            collect: Collects one generation (0, 1 or 2) and everything younger.
            clock: Monotonic seconds, to time each pass.
        """
        self._collect = collect
        self._clock = clock
        self.active = False
        self.suspended = False
        self._estimate_s = [_FIRST_ESTIMATE_S] * (_OLDEST + 1)
        self._passes = [0] * _OLDEST  # of generation n since generation n + 1 was collected
        self._last_pass_at = 0.0

    def begin(self) -> None:
        """Turn automatic collection off and freeze what is alive. Does nothing if active."""
        if self.active:
            return
        gc.collect(1)
        gc.freeze()
        gc.disable()
        self.active = True
        self.suspended = False
        self._passes = [0] * _OLDEST
        self._last_pass_at = self._clock()

    def suspend(self) -> None:
        """Turn automatic collection on until ``resume()``: no ticks are running."""
        if self.active and not self.suspended:
            gc.enable()
            self.suspended = True

    def resume(self) -> None:
        """Turn automatic collection off again after ``suspend()``."""
        if self.active and self.suspended:
            gc.disable()
            self.suspended = False
            self._last_pass_at = self._clock()

    def end(self) -> None:
        """Turn automatic collection back on and unfreeze. Does nothing if not active."""
        if not self.active:
            return
        gc.unfreeze()
        gc.enable()
        self.active = False
        self.suspended = False

    def due_generation(self) -> int:
        """The generation the next pass collects: 0, 1 or 2."""
        generation = 0
        while generation < _OLDEST and self._passes[generation] >= _PASSES_PER_OLDER:
            generation += 1
        return generation

    def collect_if_time(self, gap_s: float) -> bool:
        """Run the pass that is due, if ``gap_s`` seconds are enough for it.

        Args:
            gap_s: Seconds until the next tick is due.

        Returns:
            True if a pass ran. Always False when not active or when suspended.
        """
        if not self.active or self.suspended:
            return False
        generation = self.due_generation()
        started = self._clock()
        overdue = started - self._last_pass_at >= _OVERDUE_S
        if gap_s < 2.0 * self._estimate_s[generation] + _MARGIN_S and not overdue:
            return False

        self._collect(generation)
        finished = self._clock()

        self._estimate_s[generation] = finished - started
        self._last_pass_at = finished
        for younger in range(generation):
            self._passes[younger] = 0
        if generation < _OLDEST:
            self._passes[generation] += 1
        return True
