"""The scheduler: when ticks happen.

Its job is small on purpose. It works out when each rate driver is next due
(``DueTimes``), sleeps until then, and calls back with the tick's time and the
drivers due at it. What a tick does is not its business.
"""

from __future__ import annotations

import gc
import time
from typing import Awaitable, Callable, Dict, Optional, Tuple

import anyio
import structlog

from rasl.graph.node import TickContext
from rasl.runtime.diagnostics import TimingStats
from rasl.runtime.timing import DueTimes

logger = structlog.get_logger()

TickCallback = Callable[[TickContext, Tuple[str, ...]], Awaitable[None]]
"""Called for each tick with its context and the rate drivers due at it."""


class Scheduler:
    """Sleeps until each tick is due and reports it.

    Sinks drive the rates: each rate driver is due at ``t0 + n / hz``, and
    drivers due at the same instant share a tick. A driver that falls more
    than one period behind jumps to its next due time; missed ticks are not
    replayed. Nothing else wakes it but ``wake()``.

    Attributes:
        t0: The instant every rate driver counts from (monotonic clock).
        tick_count: Ticks run since ``start()``.
    """

    def __init__(self, timing: TimingStats) -> None:
        """
        Args:
            timing: Where tick latency and dropped ticks are recorded.
        """
        self._timing = timing
        self.t0: float = 0.0
        self.tick_count: int = 0
        # Set by wake() to end a sleep early (made in start(), inside the loop)
        self._wake: Optional[anyio.Event] = None
        # GC optimization: automatic GC is off while ticks run
        self._gc_disabled = False

    def start(self) -> None:
        """Start counting time. Call from inside the event loop."""
        self.t0 = time.monotonic()
        self.tick_count = 0
        self._wake = anyio.Event()

    def stop(self) -> None:
        """Undo what running changed outside this object."""
        if self._gc_disabled:
            gc.enable()
            self._gc_disabled = False

    def wake(self) -> None:
        """End the current sleep, so the caller's ``should_stop`` is looked at now."""
        if self._wake is not None:
            self._wake.set()

    def rearm(self) -> None:
        """Be ready for the next ``wake()``."""
        self._wake = anyio.Event()

    async def idle(self, should_stop: Callable[[], bool]) -> None:
        """Wait for ``wake()``: with no rate driver there is nothing to time."""
        assert self._wake is not None
        if not should_stop():
            await self._wake.wait()

    async def _sleep_until(self, target_time: float, should_stop: Callable[[], bool]) -> bool:
        """Sleep until a tick is due, or until woken to stop.

        Returns:
            False if the time had already passed and nothing was awaited.
        """
        assert self._wake is not None
        now = time.monotonic()
        if now >= target_time:
            return False

        # Run GC during sleep if we have enough time budget (>25ms remaining).
        # Use 25ms threshold to ensure GC completes before the next tick even
        # if it takes 15-20ms.
        if target_time - now > 0.025:
            gc.collect(0)  # Only gen0 for speed
            now = time.monotonic()

        while now < target_time and not should_stop():
            with anyio.move_on_after(target_time - now):
                await self._wake.wait()
            now = time.monotonic()
        return True

    async def run(
        self,
        rates: Dict[str, float],
        on_tick: TickCallback,
        should_stop: Callable[[], bool],
        *,
        resume: bool = False,
    ) -> None:
        """Run ticks until ``should_stop()`` is true at a tick boundary.

        Args:
            rates: Rate in Hz of each rate driver, by node id.
            on_tick: Called for each tick.
            should_stop: Looked at before every tick and after every sleep.
            resume: False at startup: every rate driver is first due at ``t0``.
                True when going on after a stop: each driver goes on at its
                first due time not yet past, still counted from ``t0``, so a
                sink that kept its rate keeps its timing.
        """
        due = DueTimes(rates, self.t0, time.monotonic() if resume else None)

        logger.info("scheduler_started", rates=rates)

        while True:
            # A tick boundary: the one place the caller may change what runs
            if should_stop():
                return

            target_time, sinks = due.next()

            if not await self._sleep_until(target_time, should_stop):
                # Running late: still let everything else on the event loop run
                # (signals, the web server, the config watch, node tasks)
                await anyio.sleep(0)
            if should_stop():
                continue

            # Track tick latency
            now = time.monotonic()
            latency_ms = (now - target_time) * 1000
            self._timing.total_ticks += 1
            self._timing.latency_samples.append(latency_ms)

            if latency_ms > self._timing.max_latency_ms:
                self._timing.max_latency_ms = latency_ms

            if latency_ms > self._timing.jitter_threshold_ms:
                self._timing.late_ticks += 1

                # Check if GC ran during this stall
                gc_info = None
                if latency_ms > 20:  # Check GC for stalls >20ms
                    gc_stats = gc.get_stats()
                    gc_info = {
                        "gen0": gc_stats[0].get("collections", 0),
                        "gen1": gc_stats[1].get("collections", 0),
                        "gen2": gc_stats[2].get("collections", 0),
                        "pending": gc.get_count(),
                    }

                logger.warning(
                    "tick_late",
                    tick=self.tick_count,
                    latency_ms=round(latency_ms, 2),
                    sinks=list(sinks),
                    gc_info=gc_info,
                    prev_tick_latency_ms=round(self._timing.latency_samples[-2], 2)
                    if len(self._timing.latency_samples) > 1
                    else None,
                )

            # Disable GC during tick execution to prevent jitter
            if not self._gc_disabled:
                gc.disable()
                self._gc_disabled = True

            # The tick is the moment it was due, not the moment it was reached:
            # nodes see evenly spaced times however the wake-up jitters.
            tick = TickContext(
                tick=self.tick_count,
                t=target_time - self.t0,
                dt=0.0,  # per node: set when the node is pulled
                wall_time=target_time,
            )
            await on_tick(tick, sinks)
            self.tick_count += 1

            now = time.monotonic()
            dropped = due.advance(sinks, now)
            if dropped:
                self._timing.record_dropped(dropped, now)

            # Periodic timing report
            if now - self._timing.last_report_time >= self._timing.report_interval:
                self._timing.report(now)
                self._timing.last_report_time = now
