"""Node protocol definition.

This module defines the Node protocol that all DAG processing nodes must
implement, along with helper functions for accessing node ports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, Union

from ..ports import EMPTY_PORTS, PortGroup, _EmptyPortGroup
from .context import NodeContext

if TYPE_CHECKING:
    from ..tick import TickContext


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
        >>> from rasl.engine.frames import MatrixPayload
        >>> from rasl.engine.ports import InputPortSpec, OutputPortSpec, PortGroup
        >>> from rasl.engine.tick import TickContext, pull_rate
        >>>
        >>> class MyTransform:
        ...     id: str = "my_transform"
        ...     inputs = PortGroup.inputs(data=InputPortSpec(MatrixPayload))
        ...     outputs = PortGroup.outputs(result=OutputPortSpec(MatrixPayload))
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
