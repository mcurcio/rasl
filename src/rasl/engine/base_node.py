"""Base node class for all RASL nodes.

This module provides the abstract base class that all node implementations
must inherit from. It handles common initialization (id, metadata) and
defines the lifecycle interface.

BaseNode also handles the `connect` directive via the config dispatch system,
collecting ConnectionSpec objects that the Graph resolves into edges.

Pull-based execution model:
    - Nodes implement pull(tick) to compute outputs from inputs
    - Read from self.inputs.<port>.read()
    - Write to self.outputs.<port>.write(frame)
    - Sinks use @pull_rate(hz) decorator to drive the scheduler

Example:
    >>> from rasl.engine.base_node import BaseNode
    >>> from rasl.engine.registry import node
    >>> from rasl.engine.tick import TickContext, pull_rate
    >>> from rasl.nodes.models import SinkNodeConfig
    >>>
    >>> @node("MySink")
    ... class MySink(BaseNode):
    ...     class Config(SinkNodeConfig):
    ...         fps: float = 30.0
    ...
    ...     @pull_rate(lambda self: self._fps)
    ...     async def pull(self, tick: TickContext) -> None:
    ...         frame = self.inputs.data.read()
    ...         if frame:
    ...             self._send(frame.payload)
"""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, ClassVar, Sequence, Type

from rasl.config.connection import ConnectionDescriptor, parse_connect_directive

if TYPE_CHECKING:
    from .frame import Frame
    from .graph import Edge
    from .node import NodeContext
    from .tick import TickContext
    from rasl.config.models import BaseNodeConfig
    from rasl.config.directive import Directive


class BaseNode(ABC):
    """Abstract base class for all nodes.

    Subclasses must:
    1. Define a nested `Config` class inheriting from a base config model
    2. Call `super().__init__(config)` in their constructor
    3. Implement pull(tick) for computation (and optionally start/stop)
    4. Define `inputs` and/or `outputs` PortGroups as class attributes

    The base class handles:
    - Setting `self.id` from config
    - Storing metadata in `self._metadata`

    Pull-based execution:
    - Read inputs via self.inputs.<port>.read()
    - Write outputs via self.outputs.<port>.write(frame)
    - Use @pull_rate(hz) on pull() for sinks to drive scheduler

    Attributes:
        id: Unique node identifier within the graph.
        Config: Class variable pointing to the nested Config class.
        inputs: Bound input ports (set by scheduler at runtime).
        outputs: Bound output ports (set by scheduler at runtime).

    Example:
        >>> @node("MyTransform")
        ... class MyTransform(BaseNode):
        ...     class Config(TransformNodeConfig):
        ...         gain: float = Field(1.0, ge=0.0)
        ...
        ...     inputs = PortGroup.inputs(data=PortSpec(accepts="array"))
        ...     outputs = PortGroup.outputs(result=PortSpec(accepts="array"))
        ...
        ...     def __init__(self, config: Config) -> None:
        ...         super().__init__(config)
        ...         self._gain = config.gain
        ...
        ...     async def pull(self, tick: TickContext) -> None:
        ...         frame = self.inputs.data.read()
        ...         if frame:
        ...             result = frame.payload.data * self._gain
        ...             self.outputs.result.write(frame.with_payload(ArrayPayload(result)))
    """

    # Subclasses define this as a nested class
    Config: ClassVar[Type["BaseNodeConfig"]]

    id: str
    """Unique node identifier within the graph."""

    # Connection descriptors collected during config parsing
    _connection_descriptors: list[ConnectionDescriptor]

    def __init__(self, config: "BaseNodeConfig") -> None:
        """Initialize base node with common config.

        Subclasses should call `super().__init__(config)` first,
        then extract their specific parameters from config.

        Args:
            config: Validated configuration instance.
        """
        self.id = config.id
        self._metadata = dict(config.metadata)
        self._connection_descriptors = []

    def parse_connect_directives(self, directive: "Directive") -> None:
        """Parse connect directives from node config block.

        Called by the loader after node construction. Extracts all
        connect directives and stores them as ConnectionDescriptors.

        Args:
            directive: The node's config directive block.
        """
        for child in directive.block:
            if child.keyword == "connect":
                desc = parse_connect_directive(child)
                self._connection_descriptors.append(desc)

    def get_connection_descriptors(self) -> list[ConnectionDescriptor]:
        """Get all connection descriptors for this node.

        Returns:
            List of ConnectionDescriptor objects to be resolved by Graph.
        """
        return self._connection_descriptors.copy()

    async def start(self, ctx: "NodeContext") -> None:
        """Initialize the node when scheduler starts.

        Called once before any pull() calls. Use this to set up resources,
        open connections, or start background tasks.

        Override in subclasses that need initialization.

        Args:
            ctx: Node context providing identity and runtime services.
        """
        pass

    async def pull(self, tick: "TickContext") -> None:
        """Process inputs and produce outputs.

        Called by the scheduler when this node needs to compute.
        Read from self.inputs.<port>.read() and write to
        self.outputs.<port>.write().

        For sinks: decorate with @pull_rate(hz) to drive the scheduler.
        For sources/transforms: called when downstream needs data.

        Override in subclasses to implement node logic.

        Args:
            tick: Timing context with tick count, t, dt, wall_time.
        """
        pass

    async def stop(self, ctx: "NodeContext") -> None:
        """Clean up the node during graceful shutdown.

        Called once when the scheduler is stopping. Use this to close
        connections, flush buffers, and release resources.

        Override in subclasses that need cleanup.

        Args:
            ctx: Node context providing identity and runtime services.
        """
        pass

    def validate_connections(self, incoming_edges: Sequence["Edge"]) -> None:
        """Validate that this node's connection requirements are met.

        Called by the graph builder after all edges are registered.
        Override in subclasses that have specific connection requirements
        (e.g., requiring certain ports to be connected).

        The default implementation does nothing—nodes without special
        connection requirements need not override this method.

        Args:
            incoming_edges: All edges targeting this node.

        Raises:
            ValueError: If connection requirements are not satisfied.
        """
        pass
