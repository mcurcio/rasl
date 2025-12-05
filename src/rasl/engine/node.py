"""Node protocol and context definitions for the RASL processing DAG.

This module defines the core abstractions for nodes in the processing
graph: the Node protocol that all nodes must implement, and the
NodeContext that provides runtime services to nodes during execution.

Node Types:
    - SourceNode: No inputs, generates frames from external sources
    - TransformNode: Receives frames, processes them, emits results
    - SinkNode: No outputs, writes frames to external targets
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol, Tuple

from .frame import Frame
from .node_config import NodeConfig


EmitCallable = Callable[[str, Frame], Awaitable[None]]
"""Type alias for the emit callback function signature.

Args:
    port: The output port name to emit on.
    frame: The Frame to send to downstream nodes.
"""

StartTaskCallable = Callable[[Callable[..., Awaitable[None]], Tuple[Any, ...]], None]
"""Type alias for background task spawning function signature."""


@dataclass(slots=True)
class NodeContext:
    """Execution context providing runtime services to nodes.

    NodeContext is passed to node lifecycle methods (start, handle, stop)
    and provides the means for nodes to interact with the runtime:
    emitting frames to downstream nodes and spawning background tasks.

    This context is created by the Runtime for each node and should not
    be instantiated directly by node implementations.

    Attributes:
        node_id: Unique identifier of the node this context belongs to.
        emit: Async callback to send frames to downstream nodes.
        _start_background: Internal callback for spawning background tasks.

    Example:
        >>> async def handle(self, port: str, frame: Frame, ctx: NodeContext):
        ...     # Process frame and emit result
        ...     result = self._process(frame)
        ...     await ctx.emit("output", result)
    """

    node_id: str
    """Unique identifier of the node this context belongs to."""

    emit: EmitCallable
    """Async callback to emit frames to connected downstream nodes."""

    config: NodeConfig | None
    """Typed configuration for this node instance, if available."""

    logger: Any
    """Structured logger instance bound to this node instance."""

    _start_background: StartTaskCallable
    """Internal callback for spawning background async tasks."""

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


class Node(Protocol):
    """Protocol defining the interface for all DAG processing nodes.

    Nodes are the fundamental processing units in the RASL graph.
    They receive frames on input ports, process them, and emit results
    on output ports. All nodes must implement this protocol.

    Node Categories:
        - SourceNode: inputs=(), owns external listeners, emits frames
        - TransformNode: Receives and transforms frames, emits results
        - SinkNode: outputs=(), writes frames to external targets

    Lifecycle:
        1. start() is called when the runtime begins execution
        2. handle() is called for each incoming frame
        3. stop() is called during graceful shutdown

    Attributes:
        id: Unique node identifier within the graph.
        inputs: Tuple of input port names this node accepts.
        outputs: Tuple of output port names this node emits on.

    Example:
        >>> class MyTransform:
        ...     id: str = "my_transform"
        ...     inputs: Tuple[str, ...] = ("input",)
        ...     outputs: Tuple[str, ...] = ("output",)
        ...
        ...     async def start(self, ctx: NodeContext) -> None:
        ...         pass  # Initialize resources
        ...
        ...     async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        ...         # Process frame and emit
        ...         await ctx.emit("output", frame)
        ...
        ...     async def stop(self, ctx: NodeContext) -> None:
        ...         pass  # Cleanup resources
    """

    id: str
    """Unique node identifier within the graph."""

    inputs: Tuple[str, ...]
    """Tuple of input port names this node accepts frames on."""

    outputs: Tuple[str, ...]
    """Tuple of output port names this node can emit frames on."""

    async def start(self, ctx: NodeContext) -> None:
        """Initialize the node when runtime execution begins.

        Called once when the runtime starts, before any frames are
        processed. Use this to set up resources, open connections,
        or start background tasks.

        Args:
            ctx: Node execution context providing runtime services.
        """
        ...

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        """Process an incoming frame.

        Called for each frame received on any input port. The node
        should process the frame and optionally emit results to
        downstream nodes via ctx.emit().

        Args:
            port: Name of the input port the frame arrived on.
            frame: The incoming Frame to process.
            ctx: Node execution context providing runtime services.
        """
        ...

    async def stop(self, ctx: NodeContext) -> None:
        """Clean up the node during graceful shutdown.

        Called once when the runtime is stopping. Use this to close
        connections, flush buffers, and release resources.

        Args:
            ctx: Node execution context providing runtime services.
        """
        ...
