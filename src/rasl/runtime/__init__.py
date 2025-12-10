"""RASL Runtime - Execution engine for the processing graph.

This package provides schedulers that execute a compiled ExecutionPlan
using anyio for async concurrency.

Two schedulers are available:
- UnifiedScheduler: Pull-based execution driven by sink frame rates (recommended)
- Runtime: Legacy push-based execution (deprecated)

Example:
    >>> from rasl.engine import GraphBuilder
    >>> from rasl.runtime import UnifiedScheduler
    >>>
    >>> builder = GraphBuilder()
    >>> # ... add nodes and edges ...
    >>> plan = builder.build()
    >>> scheduler = UnifiedScheduler(plan)
    >>> await scheduler.run()
"""

from .monitor import NodeMonitor, NodeStats
from .scheduler import Runtime, RuntimeConfig
from .unified import UnifiedScheduler

__all__ = [
    "Runtime",
    "RuntimeConfig",
    "NodeMonitor",
    "NodeStats",
    "UnifiedScheduler",
]
