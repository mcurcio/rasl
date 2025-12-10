"""Node protocol and context definitions for the RASL processing DAG.

This module defines the core abstractions for nodes in the processing
graph: the Node protocol that all nodes must implement, and the
NodeContext that provides runtime services to nodes during execution.

Node Types:
    - SourceNode: No inputs, generates frames from external sources
    - TransformNode: Receives frames, processes them, emits results
    - SinkNode: No outputs, writes frames to external targets

Execution Model:
    - pull(): Called by scheduler when node needs to produce output
    - Nodes read from self.inputs.<port>.read() and write to self.outputs.<port>.write()
    - Timing info is in TickContext, not NodeContext
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Protocol, Tuple, Union

from .frame import Frame
from .ports import EMPTY_PORTS, PortGroup, _EmptyPortGroup

if TYPE_CHECKING:
    from .tick import TickContext


EmitCallable = Callable[[str, Frame], Awaitable[None]]
"""Type alias for the emit callback function signature (legacy).

Args:
    port: The output port name to emit on.
    frame: The Frame to send to downstream nodes.
"""

StartTaskCallable = Callable[[Callable[..., Awaitable[None]], Tuple[Any, ...]], None]
"""Type alias for background task spawning function signature."""

InjectCallable = Callable[[str, Frame], None]
"""Type alias for frame injection function signature."""


@dataclass(slots=True)
class NodeContext:
    """Node identity and runtime services.

    Passed to start(), stop(), and stored as self._ctx for use during
    pull() execution. Does NOT contain timing information - that's in
    TickContext.

    This context is created by the Scheduler for each node and should not
    be instantiated directly by node implementations.

    Attributes:
        node_id: Unique identifier of the node this context belongs to.
        logger: Structured logger instance bound to this node.

    Example:
        >>> async def start(self, ctx: NodeContext):
        ...     self._ctx = ctx
        ...     ctx.start_background(self._receive_loop)
        ...
        >>> async def _receive_loop(self):
        ...     while True:
        ...         data = await self._socket.recv()
        ...         self._ctx.inject("out", Frame(...))
    """

    node_id: str
    """Unique identifier of the node this context belongs to."""

    logger: Any
    """Structured logger instance bound to this node instance."""

    _start_background: StartTaskCallable
    """Internal callback for spawning background async tasks."""

    _inject: InjectCallable
    """Internal callback for injecting pushed frames."""

    # Legacy emit callback (for backwards compatibility during transition)
    emit: EmitCallable | None = None
    """Legacy: Async callback to emit frames. Use outputs.write() instead."""

    def start_background(self, func: Callable[..., Awaitable[None]], *args: Any) -> None:
        """Spawn a background async task within the node's task group.

        Use this to start long-running async operations that should run
        alongside the node's main processing loop. Background tasks are
        automatically cancelled when the node stops.

        Args:
            func: Async function to run in the background.
            *args: Positional arguments to pass to the function.

        Example:
            >>> async def start(self, ctx: NodeContext):
            ...     ctx.start_background(self._heartbeat_loop, interval=1.0)
        """
        self._start_background(func, args)

    def inject(self, port: str, frame: Frame) -> None:
        """Inject a frame into the graph (for push sources).

        Frame will be processed at the next scheduler tick.
        Use this from background tasks that receive external data.

        Args:
            port: Output port name to inject on.
            frame: The frame to inject.

        Example:
            >>> async def _receive_loop(self):
            ...     while True:
            ...         packet = await self._socket.recv()
            ...         frame = Frame(payload=ArrayPayload(packet.data), ...)
            ...         self._ctx.inject("dmx", frame)
        """
        self._inject(port, frame)


class Node(Protocol):
    """Protocol defining the interface for all DAG processing nodes.

    Nodes are the fundamental processing units in the RASL graph.
    They read from input ports, process data, and write to output ports.

    Node Categories:
        - SourceNode: No inputs, generates frames (e.g., Waveform)
        - TransformNode: Has both inputs and outputs (e.g., Color, Compose)
        - SinkNode: No outputs, consumes frames (e.g., DdpSink)

    Execution Model:
        1. start() is called when the scheduler begins
        2. pull() is called when the node needs to produce output
        3. stop() is called during graceful shutdown

    For pull-based execution:
        - Read inputs via self.inputs.<port>.read()
        - Write outputs via self.outputs.<port>.write()
        - Use @pull_rate decorator on pull() to drive scheduler

    Attributes:
        id: Unique node identifier within the graph.
        inputs: PortGroup of input port specs (optional, omit for sources).
        outputs: PortGroup of output port specs (optional, omit for sinks).

    Example:
        >>> from rasl.engine.ports import PortGroup, PortSpec
        >>> from rasl.engine.tick import TickContext, pull_rate
        >>>
        >>> class MyTransform:
        ...     id: str = "my_transform"
        ...     inputs = PortGroup.inputs(data=PortSpec(accepts="array"))
        ...     outputs = PortGroup.outputs(result=PortSpec(accepts="array"))
        ...
        ...     async def start(self, ctx: NodeContext) -> None:
        ...         self._ctx = ctx
        ...
        ...     async def pull(self, tick: TickContext) -> None:
        ...         frame = self.inputs.data.read()
        ...         if frame:
        ...             result = self._process(frame.payload)
        ...             self.outputs.result.write(frame.with_payload(result))
        ...
        ...     async def stop(self, ctx: NodeContext) -> None:
        ...         pass
    """

    id: str
    """Unique node identifier within the graph."""

    # inputs and outputs are optional - omit for source/sink nodes
    # inputs: PortGroup
    # outputs: PortGroup

    async def start(self, ctx: NodeContext) -> None:
        """Initialize the node when scheduler starts.

        Called once before any pull() calls. Use this to set up resources,
        open connections, or start background tasks.

        Args:
            ctx: Node context providing identity and runtime services.
        """
        ...

    async def pull(self, tick: "TickContext") -> None:
        """Process inputs and produce outputs.

        Called by the scheduler when this node needs to compute.
        Read from self.inputs.<port>.read() and write to
        self.outputs.<port>.write().

        For sinks: decorate with @pull_rate(hz) to drive the scheduler.
        For sources/transforms: called when downstream needs data.

        Args:
            tick: Timing context with tick count, t, dt, wall_time.
        """
        ...

    async def stop(self, ctx: NodeContext) -> None:
        """Clean up the node during graceful shutdown.

        Called once when the scheduler is stopping. Use this to close
        connections, flush buffers, and release resources.

        Args:
            ctx: Node context providing identity and runtime services.
        """
        ...


def get_inputs(node: Node) -> Union[PortGroup, _EmptyPortGroup]:
    """Get node's input ports, defaulting to empty.

    Checks instance attribute first (for dynamic ports), then class-level.

    Args:
        node: The node to get inputs from.

    Returns:
        The node's inputs PortGroup, or EMPTY_PORTS if not defined.
    """
    # Check instance attribute first (for dynamic ports like ComposeNode)
    if "inputs" in node.__dict__:
        inputs = node.__dict__["inputs"]
        if inputs is not None and isinstance(inputs, PortGroup):
            return inputs
    # Fall back to class-level inputs
    cls = type(node)
    if hasattr(cls, "inputs") and not isinstance(getattr(cls, "inputs"), property):
        return getattr(cls, "inputs")
    return EMPTY_PORTS


def get_outputs(node: Node) -> Union[PortGroup, _EmptyPortGroup]:
    """Get node's output ports, defaulting to empty.

    Checks instance attribute first (for dynamic ports), then class-level.

    Args:
        node: The node to get outputs from.

    Returns:
        The node's outputs PortGroup, or EMPTY_PORTS if not defined.
    """
    # Check instance attribute first (for dynamic ports)
    if "outputs" in node.__dict__:
        outputs = node.__dict__["outputs"]
        if outputs is not None and isinstance(outputs, PortGroup):
            return outputs
    # Fall back to class-level outputs
    cls = type(node)
    if hasattr(cls, "outputs") and not isinstance(getattr(cls, "outputs"), property):
        return getattr(cls, "outputs")
    return EMPTY_PORTS
