"""Unified push/pull scheduler for RASL graph execution.

This module provides the UnifiedScheduler which orchestrates pull-based
execution driven by sink frame rates, with support for push sources.

Key features:
- Sinks declare rates via @pull_rate decorator
- Computes exact tick times to hit all rates precisely
- Push events processed at next tick (wakes scheduler from sleep)
- Frame caching prevents redundant computation
- Cycle handling via previous-tick values for back-edges
"""

from __future__ import annotations

import contextlib
import gc
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import anyio
import numpy as np
import structlog

from rasl.engine.frames import Frame
from rasl.engine.graph import Edge, ExecutionPlan, InputPortProgram
from typing import Any
from rasl.engine.nodes import Node, NodeContext, get_inputs, get_outputs
from rasl.engine.ports import InputPort, OutputPort, PortGroup
from rasl.engine.tick import TickContext
from rasl.runtime.monitor import NodeMonitor

logger = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class TickSlot:
    """A scheduled moment when sinks should be pulled."""

    time_offset: float
    """Seconds from cycle start."""

    sinks: frozenset[str]
    """Sink node IDs to pull at this moment."""


@dataclass
class PushedFrame:
    """A frame injected by a push source."""

    node_id: str
    port: str
    frame: Frame
    arrival_time: float


@dataclass
class NodeRuntime:
    """Runtime state for a single node."""

    node: Node
    bound_inputs: PortGroup | None
    bound_outputs: PortGroup | None
    ctx: NodeContext
    last_invoke_time: float = 0.0


@dataclass
class TickTrace:
    """Detailed timing trace for a single tick."""
    
    tick: int
    sink_id: str
    start_time: float
    node_timings: List[Tuple[str, float, float]] = field(default_factory=list)  # (node_id, duration_ms, cumulative_ms)
    slice_timings: List[Tuple[str, str, float]] = field(default_factory=list)  # (source, target, duration_ms)
    total_ms: float = 0.0
    
    def add_node(self, node_id: str, duration_ms: float) -> None:
        cumulative = sum(t[1] for t in self.node_timings) + duration_ms
        self.node_timings.append((node_id, round(duration_ms, 3), round(cumulative, 3)))
    
    def add_slice(self, source: str, target: str, duration_ms: float) -> None:
        self.slice_timings.append((source, target, round(duration_ms, 3)))
    
    def finalize(self, end_time: float) -> None:
        self.total_ms = (end_time - self.start_time) * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tick": self.tick,
            "sink": self.sink_id,
            "total_ms": round(self.total_ms, 2),
            "nodes": {n: {"ms": d, "cumulative": c} for n, d, c in self.node_timings},
            "slices": {f"{s}->{t}": ms for s, t, ms in self.slice_timings} if self.slice_timings else None,
        }


@dataclass
class TimingStats:
    """Timing diagnostics for scheduler performance monitoring."""

    # Per-sink tracking
    sink_last_pull: Dict[str, float] = field(default_factory=dict)
    sink_target_interval: Dict[str, float] = field(default_factory=dict)
    
    # Latency tracking (rolling window)
    latency_samples: deque = field(default_factory=lambda: deque(maxlen=100))
    pull_duration_samples: Dict[str, deque] = field(default_factory=dict)
    
    # Per-node timing (rolling window per node)
    node_duration_samples: Dict[str, deque] = field(default_factory=dict)
    
    # Jitter detection
    jitter_threshold_ms: float = 10.0  # Log warning if >10ms late
    slow_tick_threshold_ms: float = 20.0  # Log detailed trace if tick takes >20ms
    last_report_time: float = 0.0
    report_interval: float = 5.0  # Report stats every 5 seconds
    
    # Counters
    total_ticks: int = 0
    late_ticks: int = 0
    max_latency_ms: float = 0.0
    
    # GC tracking
    gc_count_at_start: Tuple[int, int, int] = (0, 0, 0)
    gc_collections: int = 0
    
    # Current tick trace (for detailed logging)
    current_trace: Optional[TickTrace] = None
    
    # Populate profiling
    profile_populate: bool = False


class UnifiedScheduler:
    """Unified push/pull scheduler for RASL graphs.

    Sinks declare their desired frame rates via @pull_rate decorator.
    The scheduler computes exact tick times to hit all rates precisely,
    then sleeps optimally between ticks.

    Push sources inject frames via ctx.inject(), which are processed
    at the next tick boundary.

    Example:
        >>> plan = builder.build()
        >>> scheduler = UnifiedScheduler(plan)
        >>> await scheduler.run()  # Blocks until shutdown
    """

    def __init__(self, plan: ExecutionPlan) -> None:
        """Initialize the scheduler with a compiled execution plan.

        Args:
            plan: ExecutionPlan from GraphBuilder.build().
        """
        self._plan = plan
        self._monitor = NodeMonitor()

        # Find rate-driving sinks
        self._rate_drivers = self._find_rate_drivers()

        # Build schedule (if any rate drivers exist)
        self._schedule = self._build_schedule() if self._rate_drivers else []

        # Push queue and wake signal
        self._push_queue: deque[PushedFrame] = deque()
        self._has_pending_push = False

        # Frame cache (per-tick): (node_id, port_name, tick) -> Frame
        self._frame_cache: Dict[Tuple[str, str, int], Frame] = {}

        # Previous outputs for back-edge handling: (node_id, port_name) -> Frame
        self._previous_outputs: Dict[Tuple[str, str], Frame] = {}

        # Cycle detection
        self._back_edges = self._find_back_edges()
        self._in_progress: Set[str] = set()
        self._pulled_this_tick: Set[Tuple[str, int]] = set()

        # Build reverse adjacency: target_node -> list of incoming edges
        self._incoming: Dict[str, List[Edge]] = defaultdict(list)
        for source, edges in plan.adjacency.items():
            for edge in edges:
                self._incoming[edge.target].append(edge)

        self._input_programs_by_node: Dict[str, List[InputPortProgram]] = defaultdict(list)
        for (target_node_id, _), program in plan.input_programs.items():
            self._input_programs_by_node[target_node_id].append(program)

        self._port_buffers: Dict[Tuple[str, str], np.ndarray] = {}

        # Runtime state (populated in run())
        self._node_runtimes: Dict[str, NodeRuntime] = {}
        self._t0: float = 0.0
        self._tick: int = 0
        self._task_group: Optional[anyio.abc.TaskGroup] = None

        # Timing diagnostics
        self._timing = TimingStats()
        for sink_id, hz in self._rate_drivers.items():
            self._timing.sink_target_interval[sink_id] = 1.0 / hz
            self._timing.pull_duration_samples[sink_id] = deque(maxlen=100)

        # GC optimization: disable automatic GC during tick execution
        self._gc_disabled_during_tick = False
        self._gc_interval_ticks = 100  # Run GC every N ticks

    def enable_profiling(self, enabled: bool = True) -> None:
        """Enable detailed profiling of populate() and node execution."""
        self._timing.profile_populate = enabled
        InputPortProgram.enable_profiling(enabled)
        if enabled:
            logger.info("profiling_enabled")

    def _find_rate_drivers(self) -> Dict[str, float]:
        """Find all nodes with @pull_rate decorated pull() methods."""
        drivers: Dict[str, float] = {}

        for node_id, node in self._plan.nodes.items():
            if not hasattr(node, "pull"):
                continue

            pull_method = getattr(node, "pull")
            if not hasattr(pull_method, "_pull_rate_hz"):
                continue

            hz = pull_method._pull_rate_hz
            if callable(hz):
                hz = hz(node)

            drivers[node_id] = float(hz)
            logger.debug("rate_driver_found", node_id=node_id, hz=hz)

        return drivers

    def _build_schedule(self) -> List[TickSlot]:
        """Build schedule hitting all sink frequencies exactly."""
        if not self._rate_drivers:
            return []

        duration = 1.0  # 1-second cycle

        # Generate all tick times
        all_ticks: List[Tuple[float, str]] = []
        for sink_id, hz in self._rate_drivers.items():
            interval = 1.0 / hz
            t = 0.0
            while t < duration - 1e-9:
                all_ticks.append((t, sink_id))
                t += interval

        all_ticks.sort(key=lambda x: x[0])

        # Merge ticks at same time
        slots: List[TickSlot] = []
        epsilon = 1e-6

        for time_offset, sink_id in all_ticks:
            if slots and abs(slots[-1].time_offset - time_offset) < epsilon:
                sinks = set(slots[-1].sinks)
                sinks.add(sink_id)
                slots[-1] = TickSlot(slots[-1].time_offset, frozenset(sinks))
            else:
                slots.append(TickSlot(time_offset, frozenset({sink_id})))

        logger.info(
            "schedule_built",
            num_slots=len(slots),
            rate_drivers=list(self._rate_drivers.keys()),
        )
        return slots

    def _find_back_edges(self) -> Set[Tuple[str, str, str, str]]:
        """Find edges that create cycles (back-edges).

        Uses DFS to detect back-edges in the graph.

        Returns:
            Set of (source, source_port, target, target_port) tuples.
        """
        back_edges: Set[Tuple[str, str, str, str]] = set()
        visited: Set[str] = set()
        in_stack: Set[str] = set()

        def dfs(node_id: str) -> None:
            visited.add(node_id)
            in_stack.add(node_id)

            for edge in self._plan.adjacency.get(node_id, []):
                if edge.target in in_stack:
                    # Back-edge found
                    back_edges.add(
                        (edge.source, edge.source_port, edge.target, edge.target_port)
                    )

                if edge.target not in visited:
                    dfs(edge.target)

            in_stack.remove(node_id)

        for node_id in self._plan.nodes:
            if node_id not in visited:
                dfs(node_id)

        if back_edges:
            logger.info("back_edges_found", count=len(back_edges))

        return back_edges

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
            return self._previous_outputs.get((node_id, port))

        frame = self._frame_cache.get((node_id, port, tick))
        if frame is None:
            frame = self._previous_outputs.get((node_id, port))
        return frame

    @property
    def monitor(self) -> NodeMonitor:
        """Access the node monitor for inspecting execution stats."""
        return self._monitor

    def inject(self, node_id: str, port: str, frame: Frame) -> None:
        """Inject a pushed frame. Processed at next tick.
        
        Note: Prefer using output_port.write() instead. This method exists
        for backwards compatibility.
        """
        self._push_queue.append(
            PushedFrame(node_id, port, frame, time.monotonic())
        )
        self._has_pending_push = True

    def _on_push_write(self, port: OutputPort) -> None:
        """Callback when a push source writes to an output port.
        
        Caches the frame in _previous_outputs so downstream pulls can access it,
        and signals the scheduler to wake up.
        """
        frame = port._frame
        if frame is not None:
            # Cache directly - no need for PushedFrame queue
            self._previous_outputs[(port._node_id, port.name)] = frame
            self._has_pending_push = True
            # logger.trace(
            #     "push_write",
            #     node_id=port._node_id,
            #     port=port.name,
            # )

    async def run(self) -> None:
        """Main scheduler loop."""
        self._t0 = time.monotonic()
        self._tick = 0

        try:
            async with anyio.create_task_group() as tg:
                self._task_group = tg

                # Initialize all nodes
                await self._initialize_nodes()

                if not self._schedule:
                    # No rate drivers - only process push events
                    await self._run_push_only()
                else:
                    await self._run_scheduled()

        finally:
            # Stop all nodes
            await self._shutdown_nodes()

    async def _initialize_nodes(self) -> None:
        """Initialize all nodes and their runtime state."""
        for node_id in self._plan.topological_order:
            node = self._plan.nodes[node_id]

            # Get port groups from node (already contain InputPort/OutputPort objects)
            inputs = get_inputs(node)
            outputs = get_outputs(node)

            # Mark connected inputs
            for edge in self._incoming[node_id]:
                port = inputs.get(edge.target_port) if inputs else None
                if port and isinstance(port, InputPort):
                    port._has_upstream = True

            # Configure output ports for push sources (no incoming edges)
            if not self._incoming[node_id] and outputs:
                for output_port in outputs:
                    if isinstance(output_port, OutputPort):
                        output_port._node_id = node_id
                        output_port._on_write = self._on_push_write

            # Create node context
            node_logger = logger.bind(node=f"{type(node).__name__}.{node_id}")

            def make_inject(nid: str):
                def _inject(port: str, frame: Frame) -> None:
                    self.inject(nid, port, frame)
                return _inject

            def make_start_background():
                def _start_background(fn: Any, args: Tuple[Any, ...]) -> None:
                    if self._task_group:
                        self._task_group.start_soon(fn, *args)
                return _start_background

            ctx = NodeContext(
                node_id=node_id,
                logger=node_logger,
                _start_background=make_start_background(),
                _inject=make_inject(node_id),
            )

            async def _emit(port: str, frame: Frame) -> None:
                out = outputs.get(port) if outputs else None
                if out is None:
                    return
                if isinstance(out, OutputPort):
                    out.write(frame)

            ctx.emit = _emit

            runtime = NodeRuntime(
                node=node,
                bound_inputs=inputs,
                bound_outputs=outputs,
                ctx=ctx,
                last_invoke_time=self._t0,
            )
            self._node_runtimes[node_id] = runtime

            # Start the node
            await node.start(ctx)
            logger.debug("node_started", node_id=node_id)

    async def _shutdown_nodes(self) -> None:
        """Stop all nodes gracefully."""
        # Re-enable GC before shutdown
        if self._gc_disabled_during_tick:
            gc.enable()
            self._gc_disabled_during_tick = False
        
        for node_id in reversed(self._plan.topological_order):
            runtime = self._node_runtimes.get(node_id)
            if runtime:
                with anyio.CancelScope(shield=True):
                    with contextlib.suppress(Exception):
                        await runtime.node.stop(runtime.ctx)
                        logger.debug("node_stopped", node_id=node_id)

    async def _run_push_only(self) -> None:
        """Run loop when no pull sinks exist."""
        logger.info("running_push_only_mode")
        while True:
            if self._push_queue:
                await self._process_push_events()
                self._has_pending_push = False
            await anyio.sleep(0.1)  # Idle polling

    async def _run_scheduled(self) -> None:
        """Run the scheduled tick loop."""
        schedule = self._schedule
        cycle_start = self._t0
        slot_index = 0

        logger.info(
            "scheduler_started",
            num_slots=len(schedule),
            rates=self._rate_drivers,
        )

        while True:
            slot = schedule[slot_index]
            target_time = cycle_start + slot.time_offset

            # Sleep until target time (or wake early if push pending)
            now = time.monotonic()
            gc_ran_this_cycle = False
            while now < target_time:
                sleep_duration = target_time - now

                if self._has_pending_push and sleep_duration > 0.001:
                    # Wake early for push work, but still yield to event loop
                    await anyio.sleep(0)
                    break

                # Run GC during sleep if we have enough time budget (>25ms remaining)
                # and haven't run it this cycle yet. Use 25ms threshold to ensure
                # GC completes before the next tick even if it takes 15-20ms.
                if not gc_ran_this_cycle and sleep_duration > 0.025:
                    gc.collect(0)  # Only gen0 for speed
                    gc_ran_this_cycle = True

                # Sleep in small chunks to check for push events and allow cancellation
                await anyio.sleep(min(sleep_duration, 0.005))
                now = time.monotonic()

            # Clear frame cache for this tick
            self._frame_cache.clear()
            self._pulled_this_tick.clear()

            # Process any pending push events
            if self._push_queue:
                await self._process_push_events()
                self._has_pending_push = False

            # Check if this tick has actual work
            now = time.monotonic()
            if now >= target_time - 0.0001:  # Within 0.1ms of target
                # Track tick latency
                latency_ms = (now - target_time) * 1000
                self._timing.total_ticks += 1
                self._timing.latency_samples.append(latency_ms)
                
                if latency_ms > self._timing.max_latency_ms:
                    self._timing.max_latency_ms = latency_ms
                
                if latency_ms > self._timing.jitter_threshold_ms:
                    self._timing.late_ticks += 1
                    
                    # Check if GC ran during this stall
                    gc_counts = gc.get_count()
                    gc_stats = gc.get_stats()
                    gc_info = None
                    if latency_ms > 20:  # Check GC for stalls >20ms
                        gc_info = {
                            "gen0": gc_stats[0].get("collections", 0),
                            "gen1": gc_stats[1].get("collections", 0),
                            "gen2": gc_stats[2].get("collections", 0),
                            "pending": gc_counts,
                        }
                    
                    logger.warning(
                        "tick_late",
                        tick=self._tick,
                        latency_ms=round(latency_ms, 2),
                        sinks=list(slot.sinks),
                        gc_info=gc_info,
                        prev_tick_duration_ms=round(self._timing.latency_samples[-2], 2) if len(self._timing.latency_samples) > 1 else None,
                    )

                # Disable GC during tick execution to prevent jitter
                if not self._gc_disabled_during_tick:
                    gc.disable()
                    self._gc_disabled_during_tick = True

                # Execute scheduled pulls
                for sink_id in slot.sinks:
                    await self._pull_sink(sink_id, target_time)

                # Periodic timing report
                if now - self._timing.last_report_time >= self._timing.report_interval:
                    self._log_timing_report(now)
                    self._timing.last_report_time = now

                # Advance to next slot
                slot_index += 1
                self._tick += 1

                if slot_index >= len(schedule):
                    slot_index = 0
                    cycle_start += 1.0  # Next cycle

    def _log_timing_report(self, now: float) -> None:
        """Log periodic timing diagnostics."""
        stats = self._timing
        
        # Calculate averages
        avg_latency = sum(stats.latency_samples) / len(stats.latency_samples) if stats.latency_samples else 0
        
        # Per-sink frame rate analysis
        sink_stats = {}
        for sink_id, samples in stats.pull_duration_samples.items():
            if samples:
                avg_duration = sum(samples) / len(samples)
                max_duration = max(samples)
                target_interval_ms = stats.sink_target_interval.get(sink_id, 0) * 1000
                
                # Check if pull duration exceeds frame budget
                if max_duration > target_interval_ms * 0.8:  # >80% of budget
                    sink_stats[sink_id] = {
                        "avg_ms": round(avg_duration, 2),
                        "max_ms": round(max_duration, 2),
                        "budget_ms": round(target_interval_ms, 2),
                        "warning": "exceeds_budget" if max_duration > target_interval_ms else "near_budget",
                    }
        
        # Get GC stats
        gc_stats = gc.get_stats()
        gc_collections = sum(s.get("collections", 0) for s in gc_stats)
        gc_delta = gc_collections - stats.gc_collections
        stats.gc_collections = gc_collections
        
        # Per-node timing stats (always report all nodes when profiling)
        node_stats = {}
        for node_id, samples in stats.node_duration_samples.items():
            if samples:
                avg_ms = sum(samples) / len(samples)
                max_ms = max(samples)
                # When profiling, report all nodes; otherwise only slow ones
                if stats.profile_populate or avg_ms > 0.5 or max_ms > 2.0:
                    node_stats[node_id] = {
                        "avg_ms": round(avg_ms, 3),
                        "max_ms": round(max_ms, 3),
                    }
        
        # Populate profiling stats
        populate_stats = None
        if stats.profile_populate:
            raw_stats = InputPortProgram.get_profile_stats()
            if raw_stats:
                populate_stats = {}
                for key, s in raw_stats.items():
                    if s["count"] > 0:
                        populate_stats[f"{key[0]}.{key[1]}"] = {
                            "avg_total_ms": round(s["total_ms"] / s["count"], 3),
                            "avg_resolve_ms": round(s["resolve_ms"] / s["count"], 3),
                            "avg_asarray_ms": round(s["asarray_ms"] / s["count"], 3),
                            "avg_buffer_ms": round(s["buffer_ms"] / s["count"], 3),
                            "avg_copy_ms": round(s["copy_ms"] / s["count"], 3),
                            "count": s["count"],
                        }
                # Clear stats for next period
                InputPortProgram.enable_profiling(True)
        
        logger.info(
            "timing_report",
            total_ticks=stats.total_ticks,
            late_ticks=stats.late_ticks,
            late_pct=round(100 * stats.late_ticks / max(stats.total_ticks, 1), 1),
            avg_latency_ms=round(avg_latency, 2),
            max_latency_ms=round(stats.max_latency_ms, 2),
            gc_collections=gc_delta,
            sink_warnings=sink_stats if sink_stats else None,
            node_stats=node_stats if node_stats else None,
            populate_stats=populate_stats,
        )

    async def _pull_sink(self, sink_id: str, target_time: float = 0.0) -> None:
        """Pull a sink and all its upstream dependencies."""
        runtime = self._node_runtimes[sink_id]
        now = time.monotonic()

        # Track inter-frame interval for this sink
        last_pull = self._timing.sink_last_pull.get(sink_id)
        if last_pull is not None:
            actual_interval = now - last_pull
            target_interval = self._timing.sink_target_interval.get(sink_id, 0)
            if target_interval > 0:
                interval_error_ms = (actual_interval - target_interval) * 1000
                # Log if frame interval is significantly off (>20% deviation)
                if abs(interval_error_ms) > target_interval * 200:  # 200ms = 20% of 1s
                    logger.warning(
                        "frame_interval_jitter",
                        sink=sink_id,
                        actual_interval_ms=round(actual_interval * 1000, 2),
                        target_interval_ms=round(target_interval * 1000, 2),
                        error_ms=round(interval_error_ms, 2),
                    )
        self._timing.sink_last_pull[sink_id] = now

        # Build tick context
        dt = now - runtime.last_invoke_time
        runtime.last_invoke_time = now

        tick = TickContext(
            tick=self._tick,
            t=now - self._t0,
            dt=dt,
            wall_time=now,
        )

        start_time = time.perf_counter()
        
        # Create tick trace for detailed timing
        self._timing.current_trace = TickTrace(
            tick=self._tick,
            sink_id=sink_id,
            start_time=start_time,
        )
        
        try:
            await self._pull_node(sink_id, tick)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._monitor.record_success(sink_id, elapsed_ms)
            
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
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._monitor.record_failure(sink_id, e, elapsed_ms)
            logger.exception("pull_failed", node_id=sink_id, error=str(e))
        finally:
            self._timing.current_trace = None

    async def _pull_node(self, node_id: str, tick: TickContext) -> None:
        """Recursively pull a node after pulling its upstream."""
        # Check if already pulled this tick
        if (node_id, tick.tick) in self._pulled_this_tick:
            return
        self._pulled_this_tick.add((node_id, tick.tick))

        node_start = time.perf_counter()
        runtime = self._node_runtimes[node_id]
        node = runtime.node

        # First, pull all upstream nodes (non back-edge), so frames exist in cache.
        for edge in self._incoming[node_id]:
            if self._is_back_edge(edge):
                continue
            await self._pull_node(edge.source, tick)

        # Populate each input port using compiled programs.
        for program in self._input_programs_by_node.get(node_id, []):
            frame = program.populate(
                tick=tick.tick,
                resolve=self._resolve_frame,
                ensure_buffer=self._ensure_port_buffer,
            )
            program.target._set_frame(frame)

        # Execute node's pull
        pull_start = time.perf_counter()
        if hasattr(node, "pull"):
            # Update dt for this specific node
            dt = tick.wall_time - runtime.last_invoke_time
            runtime.last_invoke_time = tick.wall_time

            node_tick = TickContext(
                tick=tick.tick,
                t=tick.t,
                dt=dt,
                wall_time=tick.wall_time,
            )
            await node.pull(node_tick)
        
        # Record node timing
        pull_ms = (time.perf_counter() - pull_start) * 1000
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
                    self._frame_cache[(node_id, output_port.name, tick.tick)] = frame
                    self._previous_outputs[(node_id, output_port.name)] = frame


    async def _process_push_events(self) -> None:
        """Process all pending push events."""
        while self._push_queue:
            pushed = self._push_queue.popleft()

            runtime = self._node_runtimes.get(pushed.node_id)
            if not runtime:
                continue

            # For push sources, the frame goes to their output
            # (they don't have inputs - they generate data)
            for output_port in runtime.bound_outputs:
                if isinstance(output_port, OutputPort) and output_port.name == pushed.port:
                    # Cache the pushed frame
                    self._frame_cache[
                        (pushed.node_id, pushed.port, self._tick)
                    ] = pushed.frame
                    self._previous_outputs[(pushed.node_id, pushed.port)] = pushed.frame
                    break

            logger.debug(
                "push_processed",
                node_id=pushed.node_id,
                port=pushed.port,
            )
