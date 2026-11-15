"""Node protocol definition.

This module defines the Node protocol that all DAG processing nodes must
implement, along with helper functions for accessing node ports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, Union

from rasl.graph.node.context import NodeContext
from rasl.graph.ports.group import EMPTY_PORTS, PortGroup, _EmptyPortGroup

if TYPE_CHECKING:
    from rasl.graph.node.tick import TickContext


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
        >>> from rasl.signal import MatrixPayload
        >>> from rasl.graph.ports import InputPortSpec, OutputPortSpec, PortGroup
        >>> from rasl.graph.node import TickContext, pull_rate
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


def _own_ports(node: Node, attribute: str) -> Union[PortGroup, _EmptyPortGroup]:
    """A node's own port group: the one it made itself, else its own clone of
    the group its class declares.

    The clone is made the first time it is asked for and kept on the node, so
    every node owns its port objects whether or not its class extends BaseNode.
    """
    own = node.__dict__.get(attribute)
    if isinstance(own, PortGroup):
        return own
    declared = getattr(type(node), attribute, None)
    if isinstance(declared, PortGroup):
        clone = declared.clone()
        node.__dict__[attribute] = clone
        return clone
    return EMPTY_PORTS


def get_inputs(node: Node) -> Union[PortGroup, _EmptyPortGroup]:
    """Get node's input ports, defaulting to empty.

    Args:
        node: The node to get inputs from.

    Returns:
        The node's own inputs PortGroup, or EMPTY_PORTS if it declares none.
    """
    return _own_ports(node, "inputs")


def get_outputs(node: Node) -> Union[PortGroup, _EmptyPortGroup]:
    """Get node's output ports, defaulting to empty.

    Args:
        node: The node to get outputs from.

    Returns:
        The node's own outputs PortGroup, or EMPTY_PORTS if it declares none.
    """
    return _own_ports(node, "outputs")
