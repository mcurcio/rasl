"""Tick context and scheduling primitives for RASL.

This module provides the timing context passed to nodes during pull execution,
and the pull_rate decorator for declaring sink frame rates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True, slots=True)
class TickContext:
    """Timing information for the current scheduler tick.

    Passed to pull() methods. Immutable - represents a single moment in time.

    Attributes:
        tick: Monotonic tick counter since scheduler start.
        t: Time since scheduler start (seconds).
        dt: Time since this node was last invoked (seconds).
        wall_time: Monotonic wall clock time for this tick.
    """

    tick: int
    """Monotonic tick counter since scheduler start."""

    t: float
    """Time since scheduler start (seconds)."""

    dt: float
    """Time since this node was last invoked (seconds)."""

    wall_time: float
    """Monotonic wall clock time for this tick."""


def pull_rate(hz: float | Callable[[Any], float]) -> Callable[[F], F]:
    """Decorator declaring that a node drives the scheduler at a specific rate.

    Apply to a node's pull() method to indicate it should be invoked at
    the specified frequency. Only sinks typically use this decorator.

    Args:
        hz: Frequency in Hz, or callable taking `self` returning Hz.
            Use callable for config-driven rates.

    Returns:
        Decorator that marks the method with _pull_rate_hz attribute.

    Example:
        @pull_rate(30)  # Fixed 30 Hz
        async def pull(self, tick: TickContext) -> None: ...

        @pull_rate(lambda self: self._config_fps)  # Config-driven
        async def pull(self, tick: TickContext) -> None: ...
    """

    def decorator(method: F) -> F:
        method._pull_rate_hz = hz  # type: ignore[attr-defined]
        return method

    return decorator
