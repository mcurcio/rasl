"""Application state for the RASL web server.

This module provides the AppState class that holds all server state,
eliminating the need for module-level globals.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Set

if TYPE_CHECKING:
    from fastapi import WebSocket
    from rasl.engine.graph import ExecutionPlan
    from rasl.runtime import Runtime


@dataclass
class AppState:
    """Application state for the RASL web server.
    
    This class holds all state needed by the web server, including
    references to the runtime and plan, connected WebSocket clients,
    and the metrics broadcast task.
    
    Attributes:
        runtime: The active Runtime instance for metrics access.
        plan: The ExecutionPlan for graph structure.
        ws_clients: Set of connected WebSocket clients.
        metrics_task: Background task for broadcasting metrics.
        start_time: Server start timestamp.
    """
    
    runtime: "Runtime"
    plan: "ExecutionPlan"
    ws_clients: Set["WebSocket"] = field(default_factory=set)
    metrics_task: Optional[asyncio.Task] = None
    start_time: float = field(default_factory=time.time)
    
    def add_client(self, websocket: "WebSocket") -> None:
        """Add a WebSocket client to the set."""
        self.ws_clients.add(websocket)
    
    def remove_client(self, websocket: "WebSocket") -> None:
        """Remove a WebSocket client from the set."""
        self.ws_clients.discard(websocket)
    
    @property
    def client_count(self) -> int:
        """Return the number of connected clients."""
        return len(self.ws_clients)
    
    @property
    def uptime_seconds(self) -> float:
        """Return the server uptime in seconds."""
        return time.time() - self.start_time
