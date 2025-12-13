"""Node context and runtime services.

This module defines NodeContext which provides runtime services to nodes
during execution, including background task spawning and frame injection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional, Tuple

if TYPE_CHECKING:
    from ..frames import Frame


EmitCallable = Callable[[str, "Frame"], Awaitable[None]]
"""Type alias for the emit callback function signature (legacy).

Args:
    port: The output port name to emit on.
    frame: The Frame to send to downstream nodes.
"""

StartTaskCallable = Callable[[Callable[..., Awaitable[None]], Tuple[Any, ...]], None]
"""Type alias for background task spawning function signature."""

InjectCallable = Callable[[str, "Frame"], None]
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

    _inject: Optional[InjectCallable] = None
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

    def inject(self, port: str, frame: "Frame") -> None:
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
        if self._inject is not None:
            self._inject(port, frame)
