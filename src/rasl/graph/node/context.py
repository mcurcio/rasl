"""Node context and runtime services.

This module defines NodeContext which provides runtime services to nodes
during execution, including background task spawning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Tuple

if TYPE_CHECKING:
    from rasl.graph.node.resources import Resources
    from rasl.graph.node.wiring import Wiring


StartTaskCallable = Callable[[Callable[..., Awaitable[None]], Tuple[Any, ...]], None]
"""Type alias for background task spawning function signature."""

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
        resources: Shared resources, opened by the first node to ask and closed
            after the last one releases them.
        wiring: Which of this node's ports the plan it was started in connects.

    Example:
        >>> async def start(self, ctx: NodeContext):
        ...     self._ctx = ctx
        ...     ctx.start_background(self._receive_loop)
        ...
        >>> async def _receive_loop(self):
        ...     while True:
        ...         data = await self._socket.recv()
        ...         self.outputs.out.write(Frame(...))  # published at the next tick
    """

    node_id: str
    """Unique identifier of the node this context belongs to."""

    logger: Any
    """Structured logger instance bound to this node instance."""

    resources: "Resources"
    """Resources this node shares with others, such as a socket (``rasl.graph.node.resources``)."""

    wiring: "Wiring"
    """Which of this node's ports the plan it was started in connects. It is not updated
    on a reroute: a class that depends on it sets ``restart_on_wiring_change``."""

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
