"""sACN/E1.31 source node for receiving DMX universe data.

This module provides SacnSourceNode, which listens for sACN (E1.31)
DMX packets on the network and emits them as normalized Frames
into the processing graph.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Iterable, List, Mapping, Optional, Tuple

import numpy as np
import sacn

from rasl.engine.frame import Frame
from rasl.engine.node import Node, NodeContext
from rasl.engine.node_config import NodeKind, SourceNodeConfig


class SacnSourceNode:
    """Source node that receives sACN (E1.31) DMX universe data.

    SacnSourceNode listens on the specified network interface for sACN
    multicast packets and converts incoming DMX data into normalized
    Frames. Each received universe is emitted as a separate Frame with
    the channel data normalized to float32 [0.0, 1.0].

    This is a SourceNode (no inputs) that emits on a single "dmx" output port.

    The node is configured via :class:`~rasl.engine.node_config.SourceNodeConfig`,
    which is normally created by the config loader from a block like:

        rasl {
            node SacnSource sacnSource {
                universes 1 2;
                bind_address "0.0.0.0";
                bind_port 5568;
                metadata "colorSpace=rgb";
            }
        }

    The loader builds a SourceNodeConfig where:

    * ``params["universes"]`` is the list of universes to listen to.
    * ``params["bind_address"]`` / ``params["bind_port"]`` select the socket.
    * optional ``params["metadata"]`` are merged into each emitted Frame.
    * ``output`` is a :class:`PortIOConfig` with ``channels=512`` and ``port="dmx"``.

    Attributes:
        id: Unique node identifier.
        inputs: Empty tuple (source node has no inputs).
        outputs: Tuple containing "dmx" output port.
    """

    inputs: Tuple[str, ...] = ()
    """Empty tuple - source nodes do not accept input frames."""

    outputs: Tuple[str, ...] = ("dmx",)
    """Output port names. Emits DMX frames on 'dmx' port."""

    def __init__(self, config: SourceNodeConfig) -> None:
        """Initialize the sACN source node.

        Args:
            config: Typed configuration for this sACN source node.

        Raises:
            ValueError: If universes is empty.
        """
        if config.kind is not NodeKind.SOURCE:
            raise ValueError("SacnSourceNode requires a source node config")

        self.id = config.id
        self._config = config

        universes_value = config.params.get("universes")
        self._universes = sorted(set(int(u) for u in universes_value or []))
        if not self._universes:
            raise ValueError("SacnSourceNode requires at least one universe")
        self._bind_address: str = str(config.params.get("bind_address", "0.0.0.0"))
        self._bind_port: int = int(config.params.get("bind_port", 5568))
        metadata = config.params.get("metadata")
        self._metadata: dict[str, Any] = dict(metadata or {})
        self._receiver: Optional[sacn.sACNreceiver] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ctx: Optional[NodeContext] = None

    async def start(self, ctx: NodeContext) -> None:
        """Start the sACN receiver and register universe listeners.

        Called by the Runtime when execution begins. Sets up the sACN
        receiver and registers callbacks for each configured universe.

        Args:
            ctx: Node execution context providing runtime services.
        """
        self._ctx = ctx
        self._loop = asyncio.get_running_loop()
        self._receiver = sacn.sACNreceiver(
            bind_address=self._bind_address, bind_port=self._bind_port
        )
        self._receiver.start()  # type: ignore[no-untyped-call]
        for universe in self._universes:
            self._receiver.register_listener(
                "universe", self._make_listener(universe), universe=universe
            )

    def _make_listener(self, universe: int) -> Any:
        """Create a callback function for a specific universe.

        The callback converts raw DMX bytes to normalized float32 values
        and emits them as Frames on the 'dmx' output port.

        Args:
            universe: The universe number this listener handles.

        Returns:
            A callback function for the sACN receiver.
        """

        def _listener(packet: Any) -> None:
            if self._ctx is None or self._loop is None:
                return
            # Normalize DMX bytes (0-255) to float32 (0.0-1.0)
            slots = np.array(packet.dmxData, dtype=np.float32) / 255.0
            timestamp = time.monotonic()
            metadata = {
                "sourceUniverse": packet.universe,
                "priority": getattr(packet, "priority", None),
                "sequence": getattr(packet, "sequence", None),
                "sourceName": getattr(packet, "sourceName", None),
                **self._metadata,
            }
            if self._loop.is_closed():
                return
            frame = Frame(
                topic=f"sacn.universe.{packet.universe}",
                timestamp=timestamp,
                payload=slots,
                metadata={k: v for k, v in metadata.items() if v is not None},
            )
            # Emit from callback thread into async context
            asyncio.run_coroutine_threadsafe(self._ctx.emit("dmx", frame), self._loop)

        return _listener

    async def handle(
        self, port: str, frame: Frame, ctx: NodeContext
    ) -> None:  # pragma: no cover
        """Handle incoming frames (no-op for source nodes).

        Source nodes do not process incoming frames. This method
        exists only to satisfy the Node protocol.

        Args:
            port: Input port name (unused).
            frame: Incoming frame (unused).
            ctx: Node context (unused).
        """
        return

    async def stop(self, ctx: NodeContext) -> None:
        """Stop the sACN receiver and release resources.

        Called by the Runtime during graceful shutdown.

        Args:
            ctx: Node execution context.
        """
        if self._receiver is not None:
            self._receiver.stop()  # type: ignore[no-untyped-call]
            self._receiver = None
