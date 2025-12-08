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

import contextlib
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import anyio
import numpy as np
import structlog
from anyio.streams.memory import MemoryObjectReceiveStream

from rasl.config.connect_parser import ResolvedSlice
from rasl.engine.frame import ArrayPayload, Frame
from rasl.engine.graph import Edge, ExecutionPlan
from rasl.engine.node import Node, NodeContext, get_inputs
from rasl.runtime.monitor import NodeMonitor, NodeStats

logger = structlog.get_logger()


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


@dataclass(slots=True)
class PortBuffer:
    """Pre-allocated buffer for a target port that receives sliced data.

    When multiple edges write sliced data to the same target port,
    this buffer accumulates the writes before dispatching.
    """

    data: np.ndarray
    """The pre-allocated numpy buffer."""

    pending_edges: int
    """Number of edges that write to this buffer (for tracking completion)."""

    received_count: int = 0
    """Number of sliced writes received this frame cycle."""


def _apply_slice(
    source_data: np.ndarray,
    source_slice: Optional[ResolvedSlice],
    target_buffer: np.ndarray,
    target_slice: Optional[ResolvedSlice],
) -> None:
    """Apply source slice to target buffer at target slice position.

    Handles mismatched lengths by taking the minimum of source and target sizes.
    This allows open-ended slices like [0:] to work with fixed-size targets.

    Args:
        source_data: Source array to read from.
        source_slice: Slice to extract from source (None = full array).
        target_buffer: Target buffer to write to.
        target_slice: Slice position in target (None = full buffer).
    """
    # Determine source range
    if source_slice is not None:
        src_start = source_slice.start
        src_end = source_slice.end if source_slice.end is not None else len(source_data)
    else:
        src_start = 0
        src_end = len(source_data)

    # Determine target range
    if target_slice is not None:
        tgt_start = target_slice.start
        tgt_end = target_slice.end if target_slice.end is not None else len(target_buffer)
    else:
        tgt_start = 0
        tgt_end = len(target_buffer)

    # Calculate actual copy length (minimum of source and target sizes)
    src_len = src_end - src_start
    tgt_len = tgt_end - tgt_start
    copy_len = min(src_len, tgt_len)

    # Copy data
    target_buffer[tgt_start:tgt_start + copy_len] = source_data[src_start:src_start + copy_len]


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
        - Apply channel slicing for partial port connections

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

        # Pre-allocate buffers for target ports that receive sliced data
        # Key: (target_node, target_port) -> PortBuffer
        self._port_buffers: Dict[Tuple[str, str], PortBuffer] = {}
        self._sliced_edges: Dict[Tuple[str, str], List[Edge]] = defaultdict(list)

        # Find all edges with slices and pre-allocate target buffers
        for source, edges in plan.adjacency.items():
            for edge in edges:
                if edge.source_slice is not None or edge.target_slice is not None:
                    key = (edge.target, edge.target_port)
                    self._sliced_edges[key].append(edge)

        # Create buffers for sliced targets
        for (target_node, target_port), edges in self._sliced_edges.items():
            node = plan.nodes[target_node]
            inputs = get_inputs(node)
            port_spec = inputs.get(target_port)
            # Determine buffer size from port spec or max target slice end
            buffer_size = port_spec.channels if port_spec.channels else 0
            # Check if any edge specifies a larger target range
            for edge in edges:
                if edge.target_slice:
                    if edge.target_slice.end:
                        # Explicit end
                        buffer_size = max(buffer_size, edge.target_slice.end)
                    elif edge.source_slice:
                        # Open-ended target: calculate from start + source length
                        src_len = (edge.source_slice.end - edge.source_slice.start
                                   if edge.source_slice.end else 0)
                        buffer_size = max(buffer_size, edge.target_slice.start + src_len)
            # Ensure minimum buffer size
            if buffer_size == 0:
                raise ValueError(f"No buffer size determined for edge {edge}")
            self._port_buffers[key] = PortBuffer(
                data=np.zeros(buffer_size, dtype=np.float32),
                pending_edges=len(edges),
            )

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
                        """Route a frame to all nodes connected to this output port.

                        Handles channel slicing: if an edge has source/target slices,
                        the data is extracted from the source slice and written to
                        a pre-allocated buffer at the target slice position.
                        """
                        edges = self._routes.get((_node_id, port), [])
                        for edge in edges:
                            target_send = streams[edge.target][0]

                            # Check if this edge uses slicing
                            if edge.source_slice is not None or edge.target_slice is not None:
                                # Get the pre-allocated buffer for this target port
                                buffer_key = (edge.target, edge.target_port)
                                port_buffer = self._port_buffers.get(buffer_key)

                                if port_buffer is not None and hasattr(frame.payload, 'data'):
                                    # Apply the slice to the buffer
                                    _apply_slice(
                                        frame.payload.data,
                                        edge.source_slice,
                                        port_buffer.data,
                                        edge.target_slice,
                                    )

                                    # Create a new frame with the buffered data
                                    # We send on every write for simplicity
                                    sliced_payload = ArrayPayload(port_buffer.data.copy())
                                    sliced_frame = Frame(
                                        topic=frame.topic,
                                        timestamp=frame.timestamp,
                                        payload=sliced_payload,
                                        metadata=frame.metadata,
                                    )
                                    await target_send.send((edge.target_port, sliced_frame))
                                else:
                                    # Fallback: send original frame if no buffer or non-array payload
                                    await target_send.send((edge.target_port, frame))
                            else:
                                # No slicing - send frame as-is
                                await target_send.send((edge.target_port, frame))

                    # Create background task spawner
                    def start_background(
                        fn: Any, args: Tuple[Any, ...]
                    ) -> None:
                        """Spawn a background task in the runtime's task group."""
                        tg.start_soon(fn, *args)

                    node_logger = logger.bind(
                        node=type(node).__name__ + "." + node_id,
                    )

                    ctx = NodeContext(
                        node_id=node_id,
                        emit=emit,
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
