"""Node lifecycle: giving each node its context, starting it, stopping it, and
telling its ports how the plan connects them."""

from __future__ import annotations

import contextlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Type

import anyio
import structlog

from rasl.graph import ExecutionPlan
from rasl.graph.node import Node, NodeContext, Resources, get_inputs, get_outputs
from rasl.graph.ports import FrameBuffers, InputPort, OutputPort, PortGroup

logger = structlog.get_logger()


@dataclass
class NodeRuntime:
    """Runtime state for a single node."""

    node: Node
    bound_inputs: PortGroup | None
    bound_outputs: PortGroup | None
    ctx: NodeContext
    last_invoke_time: float = 0.0
    """The tick time this node last ran at (its start time before its first run)."""
    background: List[anyio.CancelScope] = field(default_factory=list)
    """One scope per background task the node started; cancelled when it is stopped."""
    stopped: bool = False
    """Set once the node is stopped, so stopping it again does nothing."""


class NodeHost:
    """Starts and stops the nodes of a plan and keeps each one's runtime state.

    Attributes:
        runtimes: The state of every node now started, by node id.
    """

    def __init__(
        self,
        *,
        resources: Resources,
        buffers: Type[FrameBuffers] = FrameBuffers,
    ) -> None:
        """
        Args:
            resources: The shared resources every node's context hands out.
            buffers: The buffers class every port gets (``DebugFrameBuffers`` in debug runs).
        """
        self.runtimes: Dict[str, NodeRuntime] = {}
        self._resources = resources
        self._buffers = buffers
        self._task_group: Optional[anyio.abc.TaskGroup] = None

    def attach(self, task_group: anyio.abc.TaskGroup) -> None:
        """Give nodes' background tasks a task group to run in."""
        self._task_group = task_group

    def bind_ports(self, plan: ExecutionPlan) -> None:
        """Tell every node's ports how the plan connects them, and give them buffers.

        Every output port, and every input port the plan feeds through slices, repeats
        or several connections, gets buffers of the host's class; a port that has them
        keeps them. Run at start and again after a plan update, since a node that keeps
        running may have gained or lost connections.
        """
        buffers = self._buffers
        incoming: Dict[str, Set[str]] = defaultdict(set)
        for edges in plan.adjacency.values():
            for edge in edges:
                incoming[edge.target].add(edge.target_port)

        for node_id, node in plan.nodes.items():
            for port in get_inputs(node):
                if not isinstance(port, InputPort):
                    continue
                connected = port.name in incoming[node_id]
                # A port that lost its last connection must not go on handing
                # out the frame that connection gave it
                if port._has_upstream and not connected:
                    port._clear()
                port._has_upstream = connected

            for output_port in get_outputs(node):
                if isinstance(output_port, OutputPort) and type(output_port._buffers) is not buffers:
                    output_port._buffers = buffers()

        for program in plan.input_programs.values():
            port = program.target
            if program.passthrough is None and type(port._buffers) is not buffers:
                port._buffers = buffers()

    async def start(self, plan: ExecutionPlan, node_id: str) -> None:
        """Give a node its runtime state and start it."""
        node = plan.nodes[node_id]

        # Get port groups from node (already contain InputPort/OutputPort objects)
        inputs = get_inputs(node)
        outputs = get_outputs(node)

        # Create node context
        node_logger = logger.bind(node=f"{type(node).__name__}.{node_id}")

        background: List[anyio.CancelScope] = []

        def _start_background(fn: Any, args: Tuple[Any, ...]) -> None:
            if self._task_group:
                # Its own scope, so stopping this node ends the task (_stop_node)
                scope = anyio.CancelScope()
                background.append(scope)

                async def _scoped() -> None:
                    with scope:
                        await fn(*args)

                self._task_group.start_soon(_scoped)

        ctx = NodeContext(
            node_id=node_id,
            logger=node_logger,
            resources=self._resources,
            wiring=plan.wiring(node_id),
            _start_background=_start_background,
        )

        # Registered before start, so a node whose start fails is still stopped
        self.runtimes[node_id] = NodeRuntime(
            node=node,
            bound_inputs=inputs,
            bound_outputs=outputs,
            ctx=ctx,
            last_invoke_time=time.monotonic(),
            background=background,
        )

        await node.start(ctx)
        logger.debug("node_started", node_id=node_id)

    async def stop(self, node_id: str) -> None:
        """Stop one node, whatever it raises, and end what it left running.

        A node's ``stop`` need not end the background tasks it started, so they
        are cancelled here. (What a stopped node's ports still hold is never
        published: the executor publishes only the ports of the running plan's
        node objects.)
        """
        runtime = self.runtimes.get(node_id)
        if runtime and not runtime.stopped:
            runtime.stopped = True
            with anyio.CancelScope(shield=True):
                with contextlib.suppress(Exception):
                    await runtime.node.stop(runtime.ctx)
                    logger.debug("node_stopped", node_id=node_id)
            for scope in runtime.background:
                scope.cancel()

    async def stop_all(self, plan: ExecutionPlan) -> None:
        """Stop every node, downstream first, then any started node ``plan`` does not
        name (one a plan update stopped partway through had not removed yet)."""
        for node_id in reversed(plan.topological_order):
            await self.stop(node_id)
        for node_id in [n for n in self.runtimes if n not in plan.nodes]:
            await self.stop(node_id)
