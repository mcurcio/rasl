"""Node lifecycle: giving each node its context, starting it, stopping it, and
telling its ports how the plan connects them."""

from __future__ import annotations

import contextlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import anyio
import structlog

from rasl.graph import ExecutionPlan
from rasl.graph.node import Node, NodeContext, get_inputs, get_outputs
from rasl.graph.ports import InputPort, OutputPort, PortGroup
from rasl.signal import Frame

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


class NodeHost:
    """Starts and stops the nodes of a plan and keeps each one's runtime state.

    Attributes:
        runtimes: The state of every node now started, by node id.
    """

    def __init__(
        self,
        *,
        on_push_write: Callable[[OutputPort], None],
        inject: Callable[[str, str, Frame], None],
    ) -> None:
        """
        Args:
            on_push_write: Called when a push source writes an output port.
            inject: Called with (node id, port, frame) when a node injects a frame.
        """
        self.runtimes: Dict[str, NodeRuntime] = {}
        self._on_push_write = on_push_write
        self._inject = inject
        self._task_group: Optional[anyio.abc.TaskGroup] = None

    def attach(self, task_group: anyio.abc.TaskGroup) -> None:
        """Give nodes' background tasks a task group to run in."""
        self._task_group = task_group

    def bind_ports(self, plan: ExecutionPlan) -> None:
        """Tell every node's ports how the plan connects them.

        Run at start and again after a plan update, since a node that keeps
        running may have gained or lost connections.

        Nodes of one class share that class's port objects unless a node makes
        its own, so a port counts as connected when any node holding it is, and
        is a push source's when any node holding it is one.
        """
        incoming: Dict[str, Set[str]] = defaultdict(set)
        for edges in plan.adjacency.values():
            for edge in edges:
                incoming[edge.target].add(edge.target_port)

        input_ports: Dict[int, InputPort] = {}
        connected: Set[int] = set()
        for node_id, node in plan.nodes.items():
            inputs = get_inputs(node)
            if not inputs:
                continue
            targets = incoming[node_id]
            for port in inputs:
                if isinstance(port, InputPort):
                    input_ports[id(port)] = port
                    if port.name in targets:
                        connected.add(id(port))
        for key, port in input_ports.items():
            # A port that lost its last connection must not go on handing out the
            # frame that connection gave it
            if port._has_upstream and key not in connected:
                port._clear()
            port._has_upstream = key in connected

        # Configure output ports for push sources (no incoming edges). In plan
        # order, as a port shared by several push sources reports the last one's id.
        for node_id in plan.topological_order:
            outputs = get_outputs(plan.nodes[node_id])
            if not incoming[node_id] and outputs:
                for output_port in outputs:
                    if isinstance(output_port, OutputPort):
                        output_port._node_id = node_id
                        output_port._on_write = self._on_push_write

    async def start(self, plan: ExecutionPlan, node_id: str) -> None:
        """Give a node its runtime state and start it."""
        node = plan.nodes[node_id]

        # Get port groups from node (already contain InputPort/OutputPort objects)
        inputs = get_inputs(node)
        outputs = get_outputs(node)

        # Create node context
        node_logger = logger.bind(node=f"{type(node).__name__}.{node_id}")

        def _inject(port: str, frame: Frame) -> None:
            self._inject(node_id, port, frame)

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
            _start_background=_start_background,
            _inject=_inject,
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

        A node's ``stop`` need not end the background tasks it started, and its
        output ports stay hooked to the runtime; left alone, a node replaced
        in a plan update would go on writing frames under its successor's id.
        """
        runtime = self.runtimes.get(node_id)
        if runtime:
            with anyio.CancelScope(shield=True):
                with contextlib.suppress(Exception):
                    await runtime.node.stop(runtime.ctx)
                    logger.debug("node_stopped", node_id=node_id)
            for scope in runtime.background:
                scope.cancel()
            if runtime.bound_outputs:
                for output_port in runtime.bound_outputs:
                    if isinstance(output_port, OutputPort):
                        output_port._on_write = None

    async def stop_all(self, plan: ExecutionPlan) -> None:
        """Stop every node, downstream first."""
        for node_id in reversed(plan.topological_order):
            await self.stop(node_id)
