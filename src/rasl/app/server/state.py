"""Application state for the RASL web server.

This module provides the AppState class that holds all server state,
eliminating the need for module-level globals.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from rasl.app.server.health import HealthReport, assess

if TYPE_CHECKING:
    from rasl.config import ConfigSession
    from rasl.graph import ExecutionPlan
    from rasl.runtime import Runtime


@dataclass
class AppState:
    """Application state for the RASL web server.
    
    This class holds all state needed by the web server, including
    references to the runtime and plan.
    
    Attributes:
        runtime: The running runtime, for metrics access.
        plan: The ExecutionPlan for graph structure.
        session: The config session, when the config is watched; health reports its
            last reload. None when it is not watched.
        start_time: Server start timestamp.
    """
    
    runtime: "Runtime"
    plan: "ExecutionPlan"
    session: Optional["ConfigSession"] = None
    start_time: float = field(default_factory=time.time)
    
    @property
    def current_plan(self) -> "ExecutionPlan":
        """The plan now running: the runtime's own when it has one (a config
        reload replaces it), else the plan the server was created with."""
        return getattr(self.runtime, "plan", self.plan)

    @property
    def uptime_seconds(self) -> float:
        """Return the server uptime in seconds."""
        return time.time() - self.start_time

    def health(self) -> HealthReport:
        """Judge the server's health now (see ``rasl.app.server.health``)."""
        scheduler = self.runtime.scheduler
        return assess(
            rates=self.runtime.rate_drivers,
            tick_count=scheduler.tick_count,
            last_tick_at=scheduler.last_tick_at,
            run_started_at=scheduler.run_started_at,
            disabled_nodes=self.runtime.executor.disabled,
            unstarted_nodes=self.runtime.executor.unstarted,
            last_reload=None if self.session is None else self.session.last_reload,
            uptime_seconds=self.uptime_seconds,
            now=time.monotonic(),
        )
