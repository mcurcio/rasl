"""Runtime scheduler for executing the RASL processing graph.

This module provides the Runtime class which executes an ExecutionPlan
using anyio for async concurrency. Each node runs in its own task with
a mailbox channel for receiving frames.

Features:
    - Per-node execution monitoring via NodeMonitor
    - Error isolation to prevent single node failures from crashing the graph
    - Frame budget monitoring with overrun warnings
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import contextlib

import anyio
import structlog

from rasl.runtime.monitor import NodeMonitor, NodeStats

logger = structlog.get_logger()
from anyio.streams.memory import MemoryObjectReceiveStream

from rasl.engine.frame import Frame
from rasl.engine.graph import Edge, ExecutionPlan
from rasl.engine.node import Node, NodeContext


@dataclass(slots=True)
class RuntimeConfig:
    """Configuration options for the Runtime.

    Attributes:
        frame_budget_ms: Maximum time (ms) allowed for processing a frame
            before logging a warning. Set to 0 to disable. Default: 16ms.
        max_consecutive_errors: Number of consecutive errors before a node
            is removed from processing. Set to None to disable. Default: None.
    """

    frame_budget_ms: float = 16.0
    max_consecutive_errors: Optional[int] = None


class Runtime:
    """Async runtime for executing a compiled graph ExecutionPlan.

    The Runtime executes the processing graph using anyio for async
    concurrency (supports both asyncio and trio backends). Each node
    runs in its own task with a dedicated mailbox channel for receiving
    frames from upstream nodes.

    Responsibilities:
        - Spawn tasks for each node in topological order
        - Route frames from node outputs to connected node inputs
        - Manage node lifecycle (start, handle, stop)
        - Provide NodeContext with emit and background task capabilities
        - Monitor node health and isolate errors
        - Track frame processing budget

    Example:
        >>> plan = builder.build()
        >>> runtime = Runtime(plan)
        >>> await runtime.run()  # Blocks until shutdown
        >>> print(runtime.get_node_stats())  # View execution metrics
    """

    def __init__(
        self,
        plan: ExecutionPlan,
        config: Optional[RuntimeConfig] = None,
    ) -> None:
        """Initialize the runtime with a compiled execution plan.

        Args:
            plan: ExecutionPlan from GraphBuilder.build() containing
                nodes, edges, and topological ordering.
            config: Optional RuntimeConfig for tuning behavior.
        """
        self._plan: ExecutionPlan = plan
        self._config: RuntimeConfig = config or RuntimeConfig()
        self._monitor: NodeMonitor = NodeMonitor()
        self._disabled_nodes: set[str] = set()
        self._routes: Dict[Tuple[str, str], List[Edge]] = defaultdict(list)
        # Build routing table: (source_node, output_port) -> list of edges
        for source, edges in plan.adjacency.items():
            for edge in edges:
                self._routes[(source, edge.source_port)].append(edge)

    @property
    def monitor(self) -> NodeMonitor:
        """Access the node monitor for inspecting execution stats."""
        return self._monitor

    def get_node_stats(self, node_id: Optional[str] = None) -> Dict[str, Any]:
        """Get execution statistics for nodes.

        Args:
            node_id: If provided, get stats for only this node.
                Otherwise returns stats for all nodes.

        Returns:
            Dictionary of node stats, JSON-serializable.
        """
        if node_id is not None:
            stats = self._monitor.get_stats(node_id)
            return stats.to_dict() if stats else {}
        return self._monitor.to_dict()

    async def run(self) -> None:
        """Execute the processing graph until shutdown.

        Creates a task for each node, wires up frame routing via
        memory streams, and runs until cancelled or all nodes complete.

        The nodes are started in topological order to ensure upstream
        nodes are ready before downstream nodes begin processing.

        Raises:
            Exception: Re-raises any unhandled exception from node tasks.
        """
        streams: Dict[
            str,
            Tuple[
                anyio.abc.ObjectSendStream[Tuple[str, Frame]],
                MemoryObjectReceiveStream[Tuple[str, Frame]],
            ],
        ] = {
            node_id: anyio.create_memory_object_stream[Tuple[str, Frame]](100)
            for node_id in self._plan.nodes
        }

        try:
            async with anyio.create_task_group() as tg:
                # Start each node in topological order
                for node_id in self._plan.topological_order:
                    node = self._plan.nodes[node_id]
                    send_stream, receive_stream = streams[node_id]

                    # Create emit function that routes to connected nodes
                    async def emit(
                        port: str, frame: Frame, *, _node_id: str = node_id
                    ) -> None:
                        """Route a frame to all nodes connected to this output port."""
                        edges = self._routes.get((_node_id, port), [])
                        for edge in edges:
                            target_send = streams[edge.target][0]
                            await target_send.send((edge.target_port, frame))

                    # Create background task spawner
                    def start_background(
                        fn: Any, args: Tuple[Any, ...]
                    ) -> None:
                        """Spawn a background task in the runtime's task group."""
                        tg.start_soon(fn, *args)

                    node_logger = logger.bind(
                        node_id=node_id,
                        node_type=type(node).__name__,
                    )

                    node_config = getattr(node, "_config", None)

                    ctx = NodeContext(
                        node_id=node_id,
                        emit=emit,
                        config=node_config,
                        logger=node_logger,
                        _start_background=start_background,
                    )
                    tg.start_soon(self._node_loop, node, send_stream, receive_stream, ctx)
        finally:
            # Ensure all streams are closed so node loops exit promptly
            for send_stream, receive_stream in streams.values():
                with contextlib.suppress(Exception):
                    await send_stream.aclose()
                with contextlib.suppress(Exception):
                    await receive_stream.aclose()

    async def _node_loop(
        self,
        node: Node,
        send: anyio.abc.ObjectSendStream[Tuple[str, Frame]],
        receive: MemoryObjectReceiveStream[Tuple[str, Frame]],
        ctx: NodeContext,
    ) -> None:
        """Main processing loop for a single node.

        Runs the node's lifecycle: start -> handle frames -> stop.
        The loop continues until the receive stream is closed or
        the task is cancelled.

        Includes error isolation: individual handle() failures are logged
        and counted but don't crash the loop. Nodes may be disabled after
        too many consecutive failures.

        Args:
            node: The Node instance to run.
            send: Memory stream for sending frames downstream.
            receive: Memory stream for receiving (port, frame) tuples.
            ctx: NodeContext providing runtime services to the node.
        """
        try:
            await node.start(ctx)
            async with receive:
                async for port, frame in receive:
                    # Skip if node has been disabled due to errors
                    if node.id in self._disabled_nodes:
                        continue

                    start_time = time.perf_counter()
                    try:
                        await node.handle(port, frame, ctx)
                        elapsed_ms = (time.perf_counter() - start_time) * 1000
                        self._monitor.record_success(node.id, elapsed_ms)

                        # Frame budget check
                        if (
                            self._config.frame_budget_ms > 0
                            and elapsed_ms > self._config.frame_budget_ms
                        ):
                            logger.warning(
                                "frame_budget_exceeded",
                                node_id=node.id,
                                elapsed_ms=round(elapsed_ms, 2),
                                budget_ms=self._config.frame_budget_ms,
                                topic=frame.topic,
                            )

                    except Exception as e:
                        elapsed_ms = (time.perf_counter() - start_time) * 1000
                        consecutive = self._monitor.record_failure(
                            node.id, e, elapsed_ms
                        )

                        # Check if node should be disabled
                        max_errors = self._config.max_consecutive_errors
                        if max_errors is not None and consecutive >= max_errors:
                            logger.error(
                                "node_disabled_due_to_errors",
                                node_id=node.id,
                                consecutive_failures=consecutive,
                                threshold=max_errors,
                            )
                            self._disabled_nodes.add(node.id)
        finally:
            # Closing the send side ensures downstream nodes unblock
            with contextlib.suppress(Exception):
                await send.aclose()
            # Ensure stop always runs, even if start/handle raised or task was cancelled
            with anyio.CancelScope(shield=True):
                with contextlib.suppress(Exception):
                    await node.stop(ctx)
