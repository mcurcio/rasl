"""The runtime: runs a compiled plan.

``Runtime`` is what an application holds. It owns the pieces and wires them:

- ``Scheduler``: when ticks happen (``rasl.runtime.scheduler``)
- ``Executor``: what a tick does, pulling sinks and what feeds them
  (``rasl.runtime.executor``)
- ``NodeHost``: starting and stopping nodes (``rasl.runtime.lifecycle``)
- ``NodeMonitor`` and ``TimingStats``: what happened, for people and the API

and it is the one place a new plan is swapped in (``request_update``).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Final, List, Optional, Set, Tuple

import anyio
import structlog

from rasl.graph import ExecutionPlan, InputPortProgram
from rasl.graph.node import TickContext
from rasl.graph.ports import DebugFrameBuffers, FrameBuffers
from rasl.runtime.diagnostics import TimingStats
from rasl.runtime.executor import Executor
from rasl.runtime.lifecycle import NodeHost, NodeRuntime
from rasl.runtime.monitor import NodeMonitor
from rasl.runtime.plan_update import PlanUpdate
from rasl.runtime.resources import ResourceRegistry
from rasl.runtime.scheduler import Scheduler
from rasl.runtime.timing import find_rate_drivers, find_undriven

logger = structlog.get_logger()

# A node a plan update could not start is retried after this many seconds, doubling
# after each failure up to the cap (owner, 2026-11-21, rasl-blc).
START_RETRY_FIRST_SECONDS: Final = 1.0
START_RETRY_MAX_SECONDS: Final = 60.0


@dataclass
class _StartRetry:
    """When to try again to start a node a plan update could not start."""

    failures: int
    due_at: float

    def failed(self, now: float) -> None:
        """Count one more failed start and push the next attempt back."""
        self.failures += 1
        self.due_at = now + start_retry_delay(self.failures)


def start_retry_delay(failures: int) -> float:
    """Seconds before the next start attempt after ``failures`` failed ones (1 or more):
    1, 2, 4, ... capped at ``START_RETRY_MAX_SECONDS``."""
    return min(START_RETRY_MAX_SECONDS, START_RETRY_FIRST_SECONDS * 2 ** (failures - 1))


class Runtime:
    """Runs an execution plan until cancelled.

    Sinks declare their desired frame rates via the @pull_rate decorator. The
    scheduler works out when each is due; at each tick the due sinks and what
    feeds them are pulled. Push sources write frames from their own background
    tasks; what a pushed output produced is published at the start of the next
    tick.

    Example:
        >>> plan = builder.build()
        >>> runtime = Runtime(plan)
        >>> await runtime.run()  # Blocks until cancelled

    Attributes:
        monitor: Per-node counts of successful and failed pulls.
        timing: Tick latency, pull durations and dropped ticks.
        scheduler: The tick timing loop.
        executor: The pull machinery and the frames between nodes.
        resources: The resources nodes share, such as sockets; closed when the runtime stops.
    """

    def __init__(
        self,
        plan: ExecutionPlan,
        *,
        max_consecutive_errors: Optional[int] = None,
        debug_frames: bool = False,
    ) -> None:
        """Set up to run a compiled execution plan.

        Args:
            plan: ExecutionPlan from GraphBuilder.build().
            max_consecutive_errors: A node whose pull() raises this many times
                in a row is disabled: it is no longer pulled, and what reads
                it goes on with the last frames it wrote. None (the default)
                never disables a node. A node replaced by a plan update
                starts afresh.
            debug_frames: Make frame-lifetime mistakes fail loudly: ports get
                ``DebugFrameBuffers`` and every frame read is checked for recycled
                data. Slower; for finding a node that keeps or forwards frames.
        """
        self._plan = plan
        self.monitor = NodeMonitor()
        self.timing = TimingStats()
        self.scheduler = Scheduler(self.timing)
        self.resources = ResourceRegistry()
        self._host = NodeHost(
            resources=self.resources,
            buffers=DebugFrameBuffers if debug_frames else FrameBuffers,
        )
        self.executor = Executor(
            self._host.runtimes,
            self.monitor,
            self.timing,
            max_consecutive_errors=max_consecutive_errors,
            debug_frames=debug_frames,
        )

        # A plan update waiting for the next tick boundary (request_update)
        self._pending_update: Optional[Tuple[PlanUpdate, anyio.Event]] = None
        # Nodes a plan update could not start, and when to try each again (on this clock)
        self._start_retries: Dict[str, _StartRetry] = {}
        self._clock = time.monotonic

        self._rate_drivers: Dict[str, float] = {}
        self._undriven: List[str] = []
        self._derive_from_plan()

    def _derive_from_plan(self) -> None:
        """Work out the rate drivers and routing tables from ``self._plan``.

        Called at construction and again after a plan update (at a tick boundary).
        """
        plan = self._plan
        # The sinks that drive the rates, and the nodes none of them reaches
        self._rate_drivers = find_rate_drivers(plan)
        self._undriven = find_undriven(plan, self._rate_drivers)
        self.executor.set_plan(plan)
        self.timing.set_rates(self._rate_drivers)

    @property
    def plan(self) -> ExecutionPlan:
        """The plan now running. A plan update replaces it at a tick boundary."""
        return self._plan

    @property
    def rate_drivers(self) -> Dict[str, float]:
        """The nodes that drive ticks, and each one's rate in Hz."""
        return dict(self._rate_drivers)

    @property
    def undriven(self) -> List[str]:
        """The nodes nothing pulls (see ``find_undriven``)."""
        return list(self._undriven)

    @property
    def unstarted(self) -> List[str]:
        """Nodes a plan update added or restarted whose ``start`` failed, sorted. They are
        not pulled, and are retried at tick boundaries after 1, 2, 4 ... seconds (at most
        a minute apart) until one succeeds or a later update removes or replaces them."""
        return sorted(self.executor.unstarted)

    @property
    def nodes(self) -> Dict[str, NodeRuntime]:
        """The runtime state of every node now started, by node id."""
        return self._host.runtimes

    def request_update(self, update: PlanUpdate) -> anyio.Event:
        """Ask for a new plan to replace the running one at the next tick boundary.

        The update names what differs (``PlanUpdate``): nodes it removes or
        replaces are stopped, nodes it adds are started, nodes that take their
        new config in place get it, and every other node keeps running
        untouched while the routing and the rates are rebuilt around it.

        Args:
            update: The new plan and how it differs from the running one.

        Returns:
            An event set once the update has been applied.

        Raises:
            RuntimeError: If an earlier update is still waiting.
        """
        if self._pending_update is not None:
            raise RuntimeError("a plan update is already waiting to be applied")
        done = anyio.Event()
        self._pending_update = (update, done)
        self.scheduler.wake()
        return done

    async def _apply_pending_update(self) -> None:
        """Swap in the waiting plan. Runs between ticks, never during one."""
        assert self._pending_update is not None
        update, done = self._pending_update
        started = time.monotonic()
        old_plan = self._plan
        try:
            # Work out the new rates and routing before anything is stopped: if
            # that fails, the old plan goes on running and nothing was touched.
            self._plan = update.plan
            try:
                self._derive_from_plan()
            except Exception as e:
                self._plan = old_plan
                self._derive_from_plan()
                logger.error("plan_update_failed", error=str(e))
                return

            # A resource the stopped nodes release and the started ones take up again
            # stays open across the swap
            async with self.resources.deferring_close():
                await self._swap_nodes(update, old_plan)

            logger.info(
                "plan_updated",
                added=list(update.added),
                removed=list(update.removed),
                restarted=list(update.restarted),
                updated=list(update.updated),
                rerouted=list(update.rerouted),
                duration_ms=round((time.monotonic() - started) * 1000, 2),
            )
        finally:
            self._pending_update = None
            self.scheduler.rearm()
            done.set()

    async def _swap_nodes(self, update: PlanUpdate, old_plan: ExecutionPlan) -> Set[str]:
        """Stop the nodes ``update`` removes or restarts, apply new settings, and start
        the nodes the new plan adds. Returns the ids of the nodes stopped."""
        # Stop what goes away: removed nodes, and old objects of replaced ones
        stopping = set(update.removed) | set(update.restarted)
        for node_id in reversed(old_plan.topological_order):
            if node_id in stopping:
                await self._host.stop(node_id)
                self._host.runtimes.pop(node_id, None)

        # A node that goes away, or is replaced, stops being retried; one the update
        # starts afresh gets its own attempt below
        for node_id in [n for n in self._start_retries if n in stopping or n not in self._plan.nodes]:
            del self._start_retries[node_id]

        # Nothing computed or measured for the old plan may leak into the new one
        self.executor.forget(stopping)
        self.timing.forget(stopping)
        self.monitor.forget(stopping)
        self.timing.set_rates(self._rate_drivers)

        # Nodes that take new settings without a restart; a node disabled for
        # failing gets another chance with them
        self.executor.disabled -= set(update.updated)
        self.monitor.end_streak(set(update.updated))
        for node_id, config in update.updated.items():
            try:
                self._plan.nodes[node_id].update_config(config)
            except Exception as e:
                logger.error("node_update_failed", node_id=node_id, error=str(e))
            retry = self._start_retries.get(node_id)
            if retry is not None:
                retry.due_at = 0.0  # new settings: try again at the next tick

        self._host.bind_ports(self._plan)
        now = self._clock()
        for node_id in self._plan.topological_order:
            if node_id not in self._host.runtimes:
                if not await self._try_start(node_id, first=True):
                    self.executor.unstarted.add(node_id)
                    self._start_retries[node_id] = _StartRetry(failures=1, due_at=now + start_retry_delay(1))
        return stopping

    async def _try_start(self, node_id: str, *, first: bool) -> bool:
        """Start a node of the running plan; on failure stop what it started and log it
        (the traceback on the first failure, one line after). Returns whether it started."""
        try:
            await self._host.start(self._plan, node_id)
            return True
        except Exception as e:
            # Release what the half-started node acquired before the next attempt
            await self._host.stop(node_id)
            retry = self._start_retries.get(node_id)
            if first:
                logger.error(
                    "node_start_failed",
                    node_id=node_id,
                    error=str(e),
                    retry_in_seconds=start_retry_delay(1),
                    exc_info=e,
                )
            else:
                failures = (retry.failures if retry else 0) + 1
                logger.warning(
                    "node_start_retry_failed",
                    node_id=node_id,
                    error=str(e),
                    failures=failures,
                    retry_in_seconds=start_retry_delay(failures),
                )
            return False

    async def _retry_starts(self) -> None:
        """At a tick boundary: try again to start each node whose retry is due."""
        now = self._clock()
        for node_id, retry in list(self._start_retries.items()):
            if now < retry.due_at:
                continue
            if await self._try_start(node_id, first=False):
                del self._start_retries[node_id]
                self.executor.unstarted.discard(node_id)
                logger.info("node_started_after_retry", node_id=node_id, failures=retry.failures)
            else:
                retry.failed(now)

    def enable_profiling(self, enabled: bool = True) -> None:
        """Enable detailed profiling of populate() and node execution."""
        self.timing.profile_populate = enabled
        InputPortProgram.enable_profiling(enabled)
        if enabled:
            logger.info("profiling_enabled")

    async def _idle(self) -> None:
        """With no rate driver, nothing ticks: wait for a plan update, and retry the
        starts that fall due meanwhile (they otherwise run at tick boundaries)."""
        while not self._update_pending():
            if not self._start_retries:
                await self.scheduler.idle(self._update_pending)
                return
            due = min(retry.due_at for retry in self._start_retries.values())
            with anyio.move_on_after(max(0.0, due - self._clock())):
                await self.scheduler.idle(self._update_pending)
                return
            await self._retry_starts()

    def _update_pending(self) -> bool:
        return self._pending_update is not None

    async def _tick(self, tick: TickContext, sinks: Tuple[str, ...]) -> None:
        """One tick: retry starts that are due, pull each sink that is due and what
        feeds it, then let shared resources finish the tick (``EndOfTick``)."""
        if self._start_retries:
            await self._retry_starts()
        self.executor.begin_tick()
        for sink_id in sinks:
            await self.executor.pull_sink(sink_id, tick)
        # Shared resources act once the tick's pulls are done (EndOfTick)
        self.resources.end_tick(tick)

    def _warn_undriven(self) -> None:
        """Say which nodes will never run, if any (see ``find_undriven``)."""
        if not self._undriven:
            return
        if self._rate_drivers:
            reason = "not upstream of any node that drives the graph at a rate"
        else:
            reason = "no node drives the graph at a rate"
        logger.warning("nodes_never_pulled", nodes=list(self._undriven), reason=reason)

    async def run(self) -> None:
        """Start every node and run ticks until cancelled; then stop every node."""
        try:
            async with anyio.create_task_group() as tg:
                self._host.attach(tg)
                self.scheduler.start()

                self._host.bind_ports(self._plan)
                for node_id in self._plan.topological_order:
                    await self._host.start(self._plan, node_id)

                # Each pass ends with a plan update, which may change what drives ticks
                resume = False
                while True:
                    self._warn_undriven()
                    if not self._rate_drivers:
                        # Nothing to pull: wait for a plan update, retrying starts meanwhile
                        await self._idle()
                    else:
                        await self.scheduler.run(
                            self._rate_drivers, self._tick, self._update_pending, resume=resume
                        )
                    await self._apply_pending_update()
                    resume = True
        finally:
            self.scheduler.stop()
            await self._host.stop_all(self._plan)
            await self.resources.close_all()
