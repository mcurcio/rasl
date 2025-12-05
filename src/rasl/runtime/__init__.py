"""RASL Runtime - Execution engine for the processing graph.

This package provides the Runtime scheduler that executes a compiled
ExecutionPlan using anyio for async concurrency.

Example:
    >>> from rasl.engine import GraphBuilder
    >>> from rasl.runtime import Runtime, RuntimeConfig
    >>>
    >>> builder = GraphBuilder()
    >>> # ... add nodes and edges ...
    >>> plan = builder.build()
    >>> config = RuntimeConfig(frame_budget_ms=16.0, max_consecutive_errors=10)
    >>> runtime = Runtime(plan, config)
    >>> await runtime.run()
    >>> print(runtime.get_node_stats())
"""

from .monitor import NodeMonitor, NodeStats
from .scheduler import Runtime, RuntimeConfig

__all__ = ["Runtime", "RuntimeConfig", "NodeMonitor", "NodeStats"]
