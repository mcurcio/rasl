"""Pulling: running a sink and everything upstream of it for one tick."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set, Tuple

import structlog

from rasl.graph import Edge, ExecutionPlan, InputPortProgram
from rasl.graph.errors import CoercionError
from rasl.graph.node import TickContext, get_outputs
from rasl.graph.ports import FrameLifetimeError, OutputPort, has_stale_data
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
    frame from the previous tick.

    Frames become visible when the executor publishes them: a pulled output at
    the end of its node's pull, a pushed output (``OutputPortSpec.pushed``, or
    any output of a node with no ``pull``) at the start of each tick, so every
    reader in a tick sees the same pushed frame (rasl-pd0.12).

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
        debug_frames: bool = False,
    ) -> None:
        """
        Args:
            nodes: The started nodes' runtime state, by id (kept by the NodeHost).
            monitor: Where each pull's success or failure is recorded.
            timing: Where pull durations are recorded.
            max_consecutive_errors: Disable a node whose pull raises this many
                times in a row, unless the node sets its own limit
                (``max_consecutive_errors`` on the node). None or 0 never disables.
            debug_frames: Check every frame read for data a port has already recycled
                (with ``DebugFrameBuffers``, which poison it), failing the reading node.
        """
        self._nodes = nodes
        self._monitor = monitor
        self._timing = timing
        self._max_consecutive_errors = max_consecutive_errors
        self.disabled: Set[str] = set()

        # Frame cache (per-tick): (node_id, port_name) -> Frame
        self._frame_cache: Dict[Tuple[str, str], Frame] = {}
        # The last frame each port published; what back-edges and pushed outputs are read from
        self.latest: Dict[Tuple[str, str], Frame] = {}
        self._pulled_this_tick: Set[str] = set()
        self._resolve = self._resolve_checked if debug_frames else self._resolve_frame

        self._plan: Optional[ExecutionPlan] = None
        self._back_edges: Set[Tuple[str, str, str, str]] = set()
        self._incoming: Dict[str, List[Edge]] = defaultdict(list)
        self._pushed_edges: Set[Edge] = set()
        self._input_programs_by_node: Dict[str, List[InputPortProgram]] = defaultdict(list)
        # Outputs published at the end of their node's pull, by node; and those published
        # at the start of each tick. Each with its (node id, port name) key.
        self._pulled_outputs: Dict[str, Tuple[Tuple[OutputPort, Tuple[str, str]], ...]] = {}
        self._pushed_outputs: Tuple[Tuple[OutputPort, Tuple[str, str]], ...] = ()

    def set_plan(self, plan: ExecutionPlan) -> None:
        """Work out the routing tables for a plan. Raises nothing it has not
        finished: the caller may fall back to the previous plan."""
        self._plan = plan
        self._back_edges = set(plan.back_edges)
        if self._back_edges:
            logger.info("back_edges_found", count=len(self._back_edges))

        # Build reverse adjacency: target_node -> list of incoming edges
        self._incoming = defaultdict(list)
        self._pushed_edges = set()
        for edges in plan.adjacency.values():
            for edge in edges:
                self._incoming[edge.target].append(edge)
                if plan.is_pushed(edge):
                    self._pushed_edges.add(edge)

        self._input_programs_by_node = defaultdict(list)
        for (target_node_id, _), program in plan.input_programs.items():
            self._input_programs_by_node[target_node_id].append(program)

        # Built from the plan's node objects, so a replaced node's old ports are in neither
        pulled: Dict[str, Tuple[Tuple[OutputPort, Tuple[str, str]], ...]] = {}
        pushed: List[Tuple[OutputPort, Tuple[str, str]]] = []
        for node_id, node in plan.nodes.items():
            pull_less = not hasattr(node, "pull")
            own: List[Tuple[OutputPort, Tuple[str, str]]] = []
            for port in get_outputs(node):
                if not isinstance(port, OutputPort):
                    continue
                entry = (port, (node_id, port.name))
                if pull_less or port.spec.pushed:
                    pushed.append(entry)
                else:
                    own.append(entry)
            pulled[node_id] = tuple(own)
        self._pulled_outputs = pulled
        self._pushed_outputs = tuple(pushed)

    def begin_tick(self) -> None:
        """Start a tick: nothing computed in an earlier tick is this tick's, and
        what pushed outputs produced since the last tick is published."""
        self._clear_tick_cache()
        latest = self.latest
        for port, key in self._pushed_outputs:
            frame = port._publish()
            if frame is not None:
                latest[key] = frame

    def _clear_tick_cache(self) -> None:
        self._frame_cache.clear()
        self._pulled_this_tick.clear()

    def forget(self, node_ids: Set[str]) -> None:
        """After a plan update stopped these nodes: nothing computed for the old
        plan may leak into the new one. Kept nodes keep their buffers, and nothing is
        published until the next tick starts."""
        self._clear_tick_cache()
        for key in [k for k in self.latest if k[0] in node_ids]:
            del self.latest[key]
        self.disabled -= node_ids

    def _is_back_edge(self, edge: Edge) -> bool:
        """Check if an edge is a back-edge (creates a cycle)."""
        return (
            edge.source,
            edge.source_port,
            edge.target,
            edge.target_port,
        ) in self._back_edges

    def _resolve_frame(self, node_id: str, port: str, is_back_edge: bool, tick: int) -> Frame | None:
        if is_back_edge:
            return self.latest.get((node_id, port))

        frame = self._frame_cache.get((node_id, port))
        if frame is None:
            frame = self.latest.get((node_id, port))
        return frame

    def _resolve_checked(self, node_id: str, port: str, is_back_edge: bool, tick: int) -> Frame | None:
        """``_resolve_frame``, raising ``FrameLifetimeError`` for a frame whose data a
        ``DebugFrameBuffers`` has recycled (debug runs only)."""
        frame = self._resolve_frame(node_id, port, is_back_edge, tick)
        if frame is not None and has_stale_data(frame):
            raise FrameLifetimeError(
                f"{node_id}.{port} handed out a frame whose data was recycled: something kept "
                "or passed on a frame past its lifetime (see Frame.detach)"
            )
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
        # A pushed output is read as last written: its node is not pulled for it.
        for edge in self._incoming[node_id]:
            if self._is_back_edge(edge) or edge in self._pushed_edges:
                continue
            await self._pull_node(edge.source, tick)

        # Execute node's pull
        pull_start = time.perf_counter()

        # Populate each input port using compiled programs. A frame the port cannot
        # take (a matrix of the wrong width for a color port) fails the node, as its
        # own pull() raising would.
        for program in self._input_programs_by_node.get(node_id, []):
            try:
                program.populate(tick=tick.tick, resolve=self._resolve)
            except (CoercionError, FrameLifetimeError) as error:
                self._node_failed(node_id, error, (time.perf_counter() - pull_start) * 1000)
                raise _NodeFailed(node_id) from error

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
                # What the failed pull produced is never published (rasl-v1e)
                for port, _ in self._pulled_outputs.get(node_id, ()):
                    port._clear()
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

        # Publish what the pull produced
        for port, key in self._pulled_outputs.get(node_id, ()):
            frame = port._publish()
            if frame is not None:
                self._frame_cache[key] = frame
                self.latest[key] = frame
