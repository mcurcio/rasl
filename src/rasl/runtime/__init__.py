"""RASL Runtime - Execution engine for the processing graph.

This package provides schedulers that execute a compiled ExecutionPlan
using anyio for async concurrency.

UnifiedScheduler runs a plan: pull-based execution driven by sink frame rates.

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
from .plan_update import PlanUpdate
from .unified import UnifiedScheduler

__all__ = [
    "NodeMonitor",
    "NodeStats",
    "PlanUpdate",
    "UnifiedScheduler",
]
