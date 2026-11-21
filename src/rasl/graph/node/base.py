"""Base node class for all RASL nodes.

This module provides the abstract base class that all node implementations
must inherit from. It handles common initialization (id, metadata) and
defines the lifecycle interface.

Pull-based execution model:
    - Nodes implement pull(tick) to compute outputs from inputs
    - Read from self.inputs.<port>.read()
    - Write to self.outputs.<port>.write(frame)
    - Sinks use @pull_rate(hz) decorator to drive the scheduler

Example:
    >>> from rasl.graph.node import NodeContext
    >>> from rasl.signal import MatrixPayload
    >>> from rasl.graph.ports import PortGroup
    >>> from rasl.graph.node import TickContext, pull_rate
    >>> from rasl.graph.node import SinkNodeConfig
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
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Sequence, Type

from rasl.graph.ports.group import PortGroup
from rasl.signal import EMPTY_METADATA

if TYPE_CHECKING:
    from rasl.graph.edge import Edge
    from rasl.graph.node.config import BaseNodeConfig
    from rasl.graph.node.context import NodeContext
    from rasl.graph.node.tick import TickContext


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

    Config reload:
    - When the config files change while the graph runs, a node whose settings
      changed is stopped and a new one is built from the new config.
    - A node that defines `update_config(self, config: Config) -> None` is kept
      running and handed its new, validated config there, between ticks. Define
      it when the node holds state worth keeping (SmoothNode does) and every
      setting can change without a restart; call `self._apply_base_config(config)` in it.

    Attributes:
        id: Unique node identifier within the graph.
        Config: Class variable pointing to the nested Config class.
        inputs: Bound input ports (set by scheduler at runtime).
        outputs: Bound output ports (set by scheduler at runtime).

    Example:
        >>> from pydantic import Field
        >>> from rasl.graph.node import BaseNode, TickContext, TransformNodeConfig, node
        >>> from rasl.graph.ports import InputPortSpec, OutputPortSpec, PortGroup
        >>> from rasl.signal import MatrixPayload
        >>>
        >>> @node("MyTransform")
        ... class MyTransform(BaseNode):
        ...     class Config(TransformNodeConfig):
        ...         gain: float = Field(1.0, ge=0.0)
        ...
        ...     inputs = PortGroup.inputs(data=InputPortSpec(MatrixPayload))
        ...     outputs = PortGroup.outputs(result=OutputPortSpec(MatrixPayload))
        ...
        ...     def __init__(self, config: Config) -> None:
        ...         super().__init__(config)
        ...         self._gain = config.gain
        ...
        ...     async def pull(self, tick: TickContext) -> None:
        ...         frame = self.inputs.data.read()
        ...         if frame:
        ...             result = frame.payload.data * self._gain
        ...             self.outputs.result.write(frame.with_payload(MatrixPayload(result)))
    """

    # Subclasses define this as a nested class
    Config: ClassVar[Type["BaseNodeConfig"]]

    id: str
    """Unique node identifier within the graph."""


    restart_on_wiring_change: ClassVar[bool] = False
    """Restart this node on a live reload that changes which of its ports have edges.

    For a node whose behaviour follows its wiring (``NodeContext.wiring``); others
    are only rerouted when their connections change.
    """

    def __init__(self, config: "BaseNodeConfig") -> None:
        """Initialize base node with common config.

        Subclasses should call `super().__init__(config)` first,
        then extract their specific parameters from config.

        Args:
            config: Validated configuration instance.
        """
        self.id = config.id
        self._apply_base_config(config)
        # The class declares the ports; this node gets its own port objects
        for attribute in ("inputs", "outputs"):
            declared = getattr(type(self), attribute, None)
            if isinstance(declared, PortGroup):
                setattr(self, attribute, declared.clone())

    def _apply_base_config(self, config: "BaseNodeConfig") -> None:
        """Take the settings every node has (at construction, and in ``update_config``):
        its frame metadata and its own error limit, ``max_consecutive_errors``."""
        md = dict(config.metadata)
        self._metadata = EMPTY_METADATA if not md else MappingProxyType(md)
        self.max_consecutive_errors: int | None = config.max_consecutive_errors

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
