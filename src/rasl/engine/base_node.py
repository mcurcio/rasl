"""Base node class for all RASL nodes.

This module provides the abstract base class that all node implementations
must inherit from. It handles common initialization (id, metadata) and
defines the lifecycle interface.

Example:
    >>> from rasl.engine.base_node import BaseNode
    >>> from rasl.engine.registry import node
    >>> from rasl.config.models import SourceNodeConfig
    >>>
    >>> @node("MySource")
    ... class MySource(BaseNode):
    ...     class Config(SourceNodeConfig):
    ...         param: float = 1.0
    ...
    ...     def __init__(self, config: Config) -> None:
    ...         super().__init__(config)
    ...         self._param = config.param
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, Sequence, Type

if TYPE_CHECKING:
    from .frame import Frame
    from .graph import Edge
    from .node import NodeContext
    from rasl.config.models import BaseNodeConfig


class BaseNode(ABC):
    """Abstract base class for all nodes.

    Subclasses must:
    1. Define a nested `Config` class inheriting from a base config model
    2. Call `super().__init__(config)` in their constructor
    3. Implement lifecycle methods: start, handle, stop
    4. Define `inputs` and/or `outputs` PortGroups as class attributes

    The base class handles:
    - Setting `self.id` from config
    - Storing metadata in `self._metadata`

    Attributes:
        id: Unique node identifier within the graph.
        Config: Class variable pointing to the nested Config class.

    Example:
        >>> @node("MyTransform")
        ... class MyTransform(BaseNode):
        ...     class Config(TransformNodeConfig):
        ...         gain: float = Field(1.0, ge=0.0)
        ...
        ...     inputs = PortGroup(data=PortSpec(accepts="array"))
        ...     outputs = PortGroup(result=PortSpec(accepts="array"))
        ...
        ...     def __init__(self, config: Config) -> None:
        ...         super().__init__(config)
        ...         self._gain = config.gain
        ...
        ...     async def start(self, ctx: NodeContext) -> None:
        ...         pass
        ...
        ...     async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        ...         # Apply gain and emit
        ...         result = frame.payload * self._gain
        ...         await ctx.emit("result", Frame(...))
        ...
        ...     async def stop(self, ctx: NodeContext) -> None:
        ...         pass
    """

    # Subclasses define this as a nested class
    Config: ClassVar[Type["BaseNodeConfig"]]

    id: str
    """Unique node identifier within the graph."""

    def __init__(self, config: "BaseNodeConfig") -> None:
        """Initialize base node with common config.

        Subclasses should call `super().__init__(config)` first,
        then extract their specific parameters from config.

        Args:
            config: Validated configuration instance.
        """
        self.id = config.id
        self._metadata = dict(config.metadata)

    @abstractmethod
    async def start(self, ctx: "NodeContext") -> None:
        """Initialize the node when runtime execution begins.

        Called once when the runtime starts, before any frames are
        processed. Use this to set up resources, open connections,
        or start background tasks.

        Args:
            ctx: Node execution context providing runtime services.
        """
        ...

    @abstractmethod
    async def handle(self, port: str, frame: "Frame", ctx: "NodeContext") -> None:
        """Process an incoming frame.

        Called for each frame received on any input port. The node
        should process the frame and optionally emit results to
        downstream nodes via ctx.emit().

        For source nodes, this method may be a no-op since they
        generate frames via background tasks rather than receiving them.

        Args:
            port: Name of the input port the frame arrived on.
            frame: The incoming Frame to process.
            ctx: Node execution context providing runtime services.
        """
        ...

    @abstractmethod
    async def stop(self, ctx: "NodeContext") -> None:
        """Clean up the node during graceful shutdown.

        Called once when the runtime is stopping. Use this to close
        connections, flush buffers, and release resources.

        Args:
            ctx: Node execution context providing runtime services.
        """
        ...

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
