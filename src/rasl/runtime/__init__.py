"""Executing a compiled plan.

- ``Runtime``: what an application holds; runs a plan and swaps in new ones
- ``Scheduler``: when ticks happen; ``DueTimes``: each rate driver's due times
- ``Executor``: what a tick does; ``NodeHost``: starting and stopping nodes
- ``PlanUpdate``: a new plan and how it differs from the one running
- ``NodeMonitor``, ``TimingStats``: what happened

Example:
    >>> from rasl.graph import GraphBuilder
    >>> from rasl.runtime import Runtime
    >>>
    >>> builder = GraphBuilder()
    >>> # ... add nodes and edges ...
    >>> runtime = Runtime(builder.build())
    >>> await runtime.run()
"""

from rasl.runtime.diagnostics import TickTrace, TimingStats
from rasl.runtime.executor import Executor
from rasl.runtime.lifecycle import NodeHost, NodeRuntime
from rasl.runtime.monitor import NodeMonitor, NodeStats
from rasl.runtime.plan_update import PlanUpdate
from rasl.runtime.runtime import Runtime
from rasl.runtime.scheduler import Scheduler
from rasl.runtime.timing import DueTimes, find_rate_drivers, find_undriven

__all__ = [
    "DueTimes",
    "Executor",
    "NodeHost",
    "NodeMonitor",
    "NodeRuntime",
    "NodeStats",
    "PlanUpdate",
    "Runtime",
    "Scheduler",
    "TickTrace",
    "TimingStats",
    "find_rate_drivers",
    "find_undriven",
]
