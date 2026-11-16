"""Pulling: running a sink and everything upstream of it for one tick."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import structlog

from rasl.graph import Edge, ExecutionPlan, InputPortProgram
from rasl.graph.errors import ComponentsError
from rasl.graph.node import TickContext
from rasl.graph.ports import OutputPort
from rasl.runtime.diagnostics import TickTrace, TimingStats
from rasl.runtime.lifecycle import NodeRuntime
from rasl.runtime.monitor import NodeMonitor
from rasl.signal import Frame

logger = structlog.get_logger()


class _NodeFailed(Exception):
    """A node's pull raised. Already recorded against that node; it only ends
    the pull of the sink being served."""

    def __init__(self, node_id: str) -> None:
        super().__init__(node_id)
        self.node_id = node_id


class Executor:
    """Pulls sinks, and holds the frames that flow between nodes.

    For one tick: each due sink is pulled, which first pulls what feeds it
    (each node at most once a tick), fills the node's input ports from the
    frames its sources wrote, and runs its ``pull``. A back-edge reads the
    frame from the previous tick. A push source's write is kept as that
    port's latest frame and read like any other.

    Attributes:
        disabled: Nodes no longer pulled because they kept failing.
        latest: The last frame each output port wrote, by (node id, port).
    """

    def __init__(
        self,
        nodes: Dict[str, NodeRuntime],
        monitor: NodeMonitor,
        timing: TimingStats,
        *,
        max_consecutive_errors: Optional[int] = None,
    ) -> None:
        """
        Args:
            nodes: The started nodes' runtime state, by id (kept by the NodeHost).
            monitor: Where each pull's success or failure is recorded.
            timing: Where pull durations are recorded.
            max_consecutive_errors: Disable a node whose pull raises this many
                times in a row, unless the node sets its own limit
                (``max_consecutive_errors`` on the node). None or 0 never disables.
        """
        self._nodes = nodes
        self._monitor = monitor
        self._timing = timing
        self._max_consecutive_errors = max_consecutive_errors
        self.disabled: Set[str] = set()

        # Frame cache (per-tick): (node_id, port_name) -> Frame
        self._frame_cache: Dict[Tuple[str, str], Frame] = {}
        # The last frame each port wrote; what back-edges and push sources are read from
        self.latest: Dict[Tuple[str, str], Frame] = {}
        self._pulled_this_tick: Set[str] = set()
        self._port_buffers: Dict[Tuple[str, str], np.ndarray] = {}

        self._plan: Optional[ExecutionPlan] = None
        self._back_edges: Set[Tuple[str, str, str, str]] = set()
        self._incoming: Dict[str, List[Edge]] = defaultdict(list)
        self._input_programs_by_node: Dict[str, List[InputPortProgram]] = defaultdict(list)

    def set_plan(self, plan: ExecutionPlan) -> None:
        """Work out the routing tables for a plan. Raises nothing it has not
        finished: the caller may fall back to the previous plan."""
        self._plan = plan
        self._back_edges = set(plan.back_edges)
        if self._back_edges:
            logger.info("back_edges_found", count=len(self._back_edges))

        # Build reverse adjacency: target_node -> list of incoming edges
        self._incoming = defaultdict(list)
        for edges in plan.adjacency.values():
            for edge in edges:
                self._incoming[edge.target].append(edge)

        self._input_programs_by_node = defaultdict(list)
        for (target_node_id, _), program in plan.input_programs.items():
            self._input_programs_by_node[target_node_id].append(program)

    def begin_tick(self) -> None:
        """Nothing computed in an earlier tick is this tick's."""
        self._frame_cache.clear()
        self._pulled_this_tick.clear()

    def forget(self, node_ids: Set[str]) -> None:
        """After a plan update stopped these nodes: nothing computed for the old
        plan may leak into the new one."""
        self.begin_tick()
        self._port_buffers.clear()
        for key in [k for k in self.latest if k[0] in node_ids]:
            del self.latest[key]
        self.disabled -= node_ids

    def store_pushed(self, node_id: str, port: str, frame: Frame) -> None:
        """Keep a frame written outside a tick as that port's latest. It is
        read at the next tick; sinks drive the rates, so nothing runs now."""
        if node_id in self._nodes:
            self.latest[(node_id, port)] = frame

    def on_push_write(self, port: OutputPort) -> None:
        """Callback when a push source writes to an output port."""
        frame = port._frame
        if frame is not None:
            self.latest[(port._node_id, port.name)] = frame

    def _is_back_edge(self, edge: Edge) -> bool:
        """Check if an edge is a back-edge (creates a cycle)."""
        return (
            edge.source,
            edge.source_port,
            edge.target,
            edge.target_port,
        ) in self._back_edges

    def _ensure_port_buffer(self, key: tuple[str, str], rows: int, cols: int) -> np.ndarray:
        buf = self._port_buffers.get(key)
        if buf is None:
            buf = np.zeros((rows, cols), dtype=np.float32)
            self._port_buffers[key] = buf
            return buf

        if buf.shape[0] < rows or buf.shape[1] < cols:
            new_buf = np.zeros(
                (max(rows, buf.shape[0]), max(cols, buf.shape[1])),
                dtype=np.float32,
            )
            new_buf[: buf.shape[0], : buf.shape[1]] = buf
            buf = new_buf
            self._port_buffers[key] = buf
        return buf

    def _resolve_frame(self, node_id: str, port: str, is_back_edge: bool, tick: int) -> Frame | None:
        if is_back_edge:
            return self.latest.get((node_id, port))

        frame = self._frame_cache.get((node_id, port))
        if frame is None:
            frame = self.latest.get((node_id, port))
        return frame

    async def pull_sink(self, sink_id: str, tick: TickContext) -> None:
        """Pull a sink and all its upstream dependencies."""
        now = time.monotonic()
        target_time = tick.wall_time

        # Track inter-frame interval for this sink
        last_pull = self._timing.sink_last_pull.get(sink_id)
        if last_pull is not None:
            actual_interval = now - last_pull
            target_interval = self._timing.sink_target_interval.get(sink_id, 0)
            if target_interval > 0:
                interval_error_ms = (actual_interval - target_interval) * 1000
                # Log if frame interval is significantly off (>20% deviation)
                threshold_ms = target_interval * 200
                if abs(interval_error_ms) > threshold_ms:
                    last_target = self._timing.sink_last_target_time.get(sink_id)
                    scheduled_interval_ms: float | None = None
                    if last_target is not None:
                        scheduled_interval_ms = (target_time - last_target) * 1000

                    common = {
                        "sink": sink_id,
                        "actual_interval_ms": round(actual_interval * 1000, 2),
                        "target_interval_ms": round(target_interval * 1000, 2),
                        "error_ms": round(interval_error_ms, 2),
                        "threshold_ms": round(threshold_ms, 2),
                        "tick": tick.tick,
                        "tick_latency_ms": round((now - target_time) * 1000, 3),
                        "scheduled_interval_ms": round(scheduled_interval_ms, 2)
                        if scheduled_interval_ms is not None
                        else None,
                    }

                    if interval_error_ms > 0:
                        logger.warning("frame_interval_late", **common)
                    else:
                        logger.info("frame_interval_early", **common)
        self._timing.sink_last_pull[sink_id] = now
        self._timing.sink_last_target_time[sink_id] = target_time

        start_time = time.perf_counter()
        
        # Create tick trace for detailed timing
        self._timing.current_trace = TickTrace(
            tick=tick.tick,
            sink_id=sink_id,
            start_time=start_time,
        )
        
        try:
            await self._pull_node(sink_id, tick)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # Track pull duration for timing diagnostics
            if sink_id in self._timing.pull_duration_samples:
                self._timing.pull_duration_samples[sink_id].append(elapsed_ms)

            # Finalize and log trace if tick was slow
            trace = self._timing.current_trace
            if trace:
                trace.finalize(time.perf_counter())
                if trace.total_ms > self._timing.slow_tick_threshold_ms:
                    logger.warning(
                        "slow_tick_trace",
                        **trace.to_dict(),
                    )
        except _NodeFailed as failed:
            # Recorded and logged against the node that raised (_pull_node);
            # this sink's pull ends here for this tick
            logger.debug("pull_abandoned", sink=sink_id, failed_node=failed.node_id)
        finally:
            self._timing.current_trace = None

    def _node_failed(self, node_id: str, error: Exception, elapsed_ms: float) -> None:
        """Record a node's failed pull, and disable the node if it keeps failing."""
        consecutive = self._monitor.record_failure(node_id, error, elapsed_ms)
        if consecutive == 1:
            # The traceback once per run of failures: rendering one costs far
            # more than a tick, and the monitor logs a line for each failure
            logger.error("pull_failed", node_id=node_id, error=str(error), exc_info=error)
        own = getattr(self._nodes[node_id].node, "max_consecutive_errors", None)
        limit = own if own is not None else self._max_consecutive_errors
        if limit and consecutive >= limit:
            self.disabled.add(node_id)
            logger.error(
                "node_disabled_due_to_errors",
                node_id=node_id,
                consecutive_failures=consecutive,
                threshold=limit,
            )

    async def _pull_node(self, node_id: str, tick: TickContext) -> None:
        """Recursively pull a node after pulling its upstream."""
        # Check if already pulled this tick
        if node_id in self._pulled_this_tick:
            return
        self._pulled_this_tick.add(node_id)

        runtime = self._nodes[node_id]
        node = runtime.node

        # A disabled node is not pulled, and pulls nothing: what reads it goes
        # on with the last frames it wrote
        if node_id in self.disabled:
            return

        # First, pull all upstream nodes (non back-edge), so frames exist in cache.
        for edge in self._incoming[node_id]:
            if self._is_back_edge(edge):
                continue
            await self._pull_node(edge.source, tick)

        # Execute node's pull
        pull_start = time.perf_counter()

        # Populate each input port using compiled programs. A frame the port cannot
        # take (a matrix of the wrong width for a color port) fails the node, as its
        # own pull() raising would.
        for program in self._input_programs_by_node.get(node_id, []):
            try:
                frame = program.populate(
                    tick=tick.tick,
                    resolve=self._resolve_frame,
                    ensure_buffer=self._ensure_port_buffer,
                )
            except ComponentsError as error:
                self._node_failed(node_id, error, (time.perf_counter() - pull_start) * 1000)
                raise _NodeFailed(node_id) from error
            program.target._set_frame(frame)

        if hasattr(node, "pull"):
            # This node's own dt: tick time since it last ran. A node shared by
            # sinks of different rates runs whenever any of them is due, so dt
            # varies from tick to tick; nodes must not assume a fixed step.
            dt = max(0.0, tick.wall_time - runtime.last_invoke_time)
            runtime.last_invoke_time = tick.wall_time

            node_tick = TickContext(
                tick=tick.tick,
                t=tick.t,
                dt=dt,
                wall_time=tick.wall_time,
            )
            try:
                await node.pull(node_tick)
            except Exception as error:
                self._node_failed(node_id, error, (time.perf_counter() - pull_start) * 1000)
                raise _NodeFailed(node_id) from error

        # Record node timing
        pull_ms = (time.perf_counter() - pull_start) * 1000
        self._monitor.record_success(node_id, pull_ms)
        if self._timing.current_trace:
            self._timing.current_trace.add_node(node_id, pull_ms)
        
        # Track per-node stats
        if node_id not in self._timing.node_duration_samples:
            self._timing.node_duration_samples[node_id] = deque(maxlen=100)
        self._timing.node_duration_samples[node_id].append(pull_ms)

        # Collect outputs and cache them
        for output_port in runtime.bound_outputs:
            if isinstance(output_port, OutputPort) and output_port.was_written:
                frame = output_port._consume()
                if frame:
                    self._frame_cache[(node_id, output_port.name)] = frame
                    self.latest[(node_id, output_port.name)] = frame
