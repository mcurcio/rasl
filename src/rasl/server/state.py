"""Application state for the RASL web server.

This module provides the AppState class that holds all server state,
eliminating the need for module-level globals.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rasl.engine.graph import ExecutionPlan
    from rasl.runtime import Runtime


@dataclass
class AppState:
    """Application state for the RASL web server.
    
    This class holds all state needed by the web server, including
    references to the runtime and plan.
    
    Attributes:
        runtime: The active Runtime instance for metrics access.
        plan: The ExecutionPlan for graph structure.
        start_time: Server start timestamp.
    """
    
    runtime: "Runtime"
    plan: "ExecutionPlan"
    start_time: float = field(default_factory=time.time)
    
    @property
    def uptime_seconds(self) -> float:
        """Return the server uptime in seconds."""
        return time.time() - self.start_time
