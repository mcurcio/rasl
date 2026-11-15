"""Server health: whether the running graph is ticking, and what has gone wrong.

``assess`` turns a snapshot of the runtime and the config session into a
``HealthReport``. It is a pure function of its arguments, so the rules below can be
tested without a running server. ``GET /health`` and the GraphQL ``health`` field
both report it.

The status, worst first:

- ``stalled``: the graph has rate-driving sinks, but no tick has finished for
  ``stall_threshold(rates)`` seconds, counted from the later of the last tick and the
  moment the scheduler last began running. The scheduler is wedged. ``GET /health``
  answers 503, so a container health check marks the container unhealthy.
- ``degraded``: the graph runs, but a node has been disabled for failing again and
  again, or the last config reload failed and the previous graph is still running.
  ``GET /health`` answers 200: the server works, and the problem is in the config or
  a device.
- ``ok``: neither.

A graph with no rate driver (an empty graph, or one whose sinks declare no rate) has
nothing to tick, so it is never stalled. Nor is a runtime whose scheduler has not
begun running yet (its nodes are still starting, e.g. connecting to devices).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from rasl.config import ReloadOutcome

# The shortest time without a tick that counts as a stall, in seconds: long enough to
# ride out a slow plan update or a GC pause at high tick rates.
MIN_STALL_SECONDS: Final = 5.0

# How many periods of the slowest rate driver may pass without a tick before the
# scheduler counts as stalled.
STALL_PERIODS: Final = 10


class HealthStatus(StrEnum):
    """The server's overall health; see the module docstring for each value."""

    OK = "ok"
    DEGRADED = "degraded"
    STALLED = "stalled"


@dataclass(frozen=True)
class HealthReport:
    """What ``GET /health`` and the GraphQL ``health`` field report.

    Attributes:
        status: The overall verdict.
        uptime_seconds: Seconds since the server was created.
        tick_count: Ticks run since the runtime started.
        last_tick_age_seconds: Seconds since the last tick finished; None if none has.
        stall_after_seconds: How long without a tick counts as a stall for the graph
            now running; None when it has no rate driver and cannot stall.
        disabled_nodes: Ids of the nodes disabled for failing again and again, sorted.
        last_reload_ok: Whether the last config reload succeeded; None if none has
            been attempted (or the config is not watched).
        last_reload_error: Why the last reload failed; None unless it failed.
        last_reload_at: When the last reload attempt ended, in Unix seconds; None if
            none has been attempted.
    """

    status: HealthStatus
    uptime_seconds: float
    tick_count: int
    last_tick_age_seconds: float | None
    stall_after_seconds: float | None
    disabled_nodes: tuple[str, ...]
    last_reload_ok: bool | None
    last_reload_error: str | None
    last_reload_at: float | None


def stall_threshold(rates: Mapping[str, float]) -> float | None:
    """Seconds without a tick after which a graph with these rate drivers is stalled.

    Args:
        rates: Each rate driver's rate in Hz, by node id.

    Returns:
        ``max(MIN_STALL_SECONDS, STALL_PERIODS / slowest rate)``, or None when there
        is no rate driver (or none with a positive rate), since nothing then ticks.
    """
    positive = [rate for rate in rates.values() if rate > 0]
    if not positive:
        return None
    return max(MIN_STALL_SECONDS, STALL_PERIODS / min(positive))


def assess(
    *,
    rates: Mapping[str, float],
    tick_count: int,
    last_tick_at: float | None,
    run_started_at: float,
    disabled_nodes: Collection[str],
    last_reload: ReloadOutcome | None,
    uptime_seconds: float,
    now: float,
) -> HealthReport:
    """Judge the server's health from a snapshot of the runtime and the config.

    Args:
        rates: The running graph's rate drivers: rate in Hz by node id.
        tick_count: Ticks run since the runtime started.
        last_tick_at: When the last tick finished (monotonic seconds), or None.
        run_started_at: When the scheduler last began running ticks (monotonic
            seconds); a tick has been due since then. 0.0 if it has not begun.
        disabled_nodes: Nodes disabled for failing again and again.
        last_reload: How the last config reload ended, or None.
        uptime_seconds: Seconds since the server was created.
        now: The current time on the same monotonic clock as ``last_tick_at``.

    Returns:
        The report, with ``status`` decided as the module docstring says.
    """
    threshold = stall_threshold(rates)
    last_tick_age = None if last_tick_at is None else now - last_tick_at

    status = HealthStatus.OK
    if disabled_nodes or (last_reload is not None and not last_reload.ok):
        status = HealthStatus.DEGRADED
    if threshold is not None and run_started_at > 0.0:
        since = max(last_tick_at or 0.0, run_started_at)
        if now - since > threshold:
            status = HealthStatus.STALLED

    return HealthReport(
        status=status,
        uptime_seconds=uptime_seconds,
        tick_count=tick_count,
        last_tick_age_seconds=last_tick_age,
        stall_after_seconds=threshold,
        disabled_nodes=tuple(sorted(disabled_nodes)),
        last_reload_ok=None if last_reload is None else last_reload.ok,
        last_reload_error=None if last_reload is None else last_reload.error,
        last_reload_at=None if last_reload is None else last_reload.at,
    )
