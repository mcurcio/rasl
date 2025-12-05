"""Node monitoring for tracking execution health and performance.

This module provides the NodeMonitor class which tracks per-node
metrics during graph execution: execution times, success/failure
counts, and error history.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger()


@dataclass(slots=True)
class NodeStats:
    """Statistics for a single node's execution.

    Tracks execution timing, success/failure counts, and the most
    recent error encountered during frame processing.

    Attributes:
        node_id: Unique identifier of the tracked node.
        handle_count: Total number of handle() calls.
        success_count: Number of successful handle() calls.
        failure_count: Number of failed handle() calls.
        consecutive_failures: Current streak of consecutive failures.
        total_execution_time_ms: Cumulative execution time in milliseconds.
        last_error: Most recent exception encountered, if any.
        last_error_time: Monotonic timestamp of last error.
    """

    node_id: str
    handle_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    total_execution_time_ms: float = 0.0
    last_error: Optional[Exception] = field(default=None, repr=False)
    last_error_time: Optional[float] = None

    @property
    def avg_execution_time_ms(self) -> float:
        """Average execution time per handle() call in milliseconds."""
        if self.handle_count == 0:
            return 0.0
        return self.total_execution_time_ms / self.handle_count

    @property
    def success_rate(self) -> float:
        """Fraction of successful handle() calls (0.0 to 1.0)."""
        if self.handle_count == 0:
            return 1.0
        return self.success_count / self.handle_count

    def to_dict(self) -> Dict[str, Any]:
        """Serialize stats to a JSON-compatible dictionary."""
        return {
            "node_id": self.node_id,
            "handle_count": self.handle_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "consecutive_failures": self.consecutive_failures,
            "total_execution_time_ms": round(self.total_execution_time_ms, 3),
            "avg_execution_time_ms": round(self.avg_execution_time_ms, 3),
            "success_rate": round(self.success_rate, 4),
            "last_error": str(self.last_error) if self.last_error else None,
            "last_error_time": self.last_error_time,
        }


class NodeMonitor:
    """Tracks execution health and performance for all nodes in a graph.

    NodeMonitor is used by the Runtime to record the outcome of each
    node's handle() call. It provides aggregated statistics for
    debugging, logging, and operational monitoring.

    Example:
        >>> monitor = NodeMonitor()
        >>> monitor.record_success("sink_1", execution_time_ms=0.5)
        >>> monitor.record_failure("sink_2", ValueError("bad data"))
        >>> stats = monitor.get_stats("sink_1")
        >>> print(stats.avg_execution_time_ms)
    """

    def __init__(self) -> None:
        """Initialize an empty monitor."""
        self._stats: Dict[str, NodeStats] = {}

    def _get_or_create(self, node_id: str) -> NodeStats:
        """Get existing stats or create new entry for a node."""
        if node_id not in self._stats:
            self._stats[node_id] = NodeStats(node_id=node_id)
        return self._stats[node_id]

    def record_success(self, node_id: str, execution_time_ms: float) -> None:
        """Record a successful handle() call for a node.

        Args:
            node_id: ID of the node that completed successfully.
            execution_time_ms: Time taken for the handle() call in milliseconds.
        """
        stats = self._get_or_create(node_id)
        stats.handle_count += 1
        stats.success_count += 1
        stats.consecutive_failures = 0
        stats.total_execution_time_ms += execution_time_ms

    def record_failure(
        self, node_id: str, error: Exception, execution_time_ms: float = 0.0
    ) -> int:
        """Record a failed handle() call for a node.

        Args:
            node_id: ID of the node that failed.
            error: The exception that was raised.
            execution_time_ms: Time taken before failure in milliseconds.

        Returns:
            The current consecutive failure count for this node.
        """
        stats = self._get_or_create(node_id)
        stats.handle_count += 1
        stats.failure_count += 1
        stats.consecutive_failures += 1
        stats.total_execution_time_ms += execution_time_ms
        stats.last_error = error
        stats.last_error_time = time.monotonic()

        logger.warning(
            "node_handle_failed",
            node_id=node_id,
            error=str(error),
            error_type=type(error).__name__,
            consecutive_failures=stats.consecutive_failures,
        )

        return stats.consecutive_failures

    def get_stats(self, node_id: str) -> Optional[NodeStats]:
        """Get statistics for a specific node.

        Args:
            node_id: ID of the node to query.

        Returns:
            NodeStats for the node, or None if not tracked.
        """
        return self._stats.get(node_id)

    def get_all_stats(self) -> Dict[str, NodeStats]:
        """Get statistics for all tracked nodes.

        Returns:
            Dictionary mapping node IDs to their NodeStats.
        """
        return self._stats.copy()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize all stats to a JSON-compatible dictionary.

        Returns:
            Dictionary with node IDs as keys and serialized stats as values.
        """
        return {node_id: stats.to_dict() for node_id, stats in self._stats.items()}

    def reset(self, node_id: Optional[str] = None) -> None:
        """Reset statistics for one or all nodes.

        Args:
            node_id: If provided, reset only this node. Otherwise reset all.
        """
        if node_id is not None:
            if node_id in self._stats:
                self._stats[node_id] = NodeStats(node_id=node_id)
        else:
            self._stats.clear()
