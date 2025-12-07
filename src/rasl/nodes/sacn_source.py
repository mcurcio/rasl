"""sACN/E1.31 source node for receiving DMX universe data.

This module provides SacnSourceNode, which listens for sACN (E1.31)
DMX packets on the network and emits them as normalized Frames
into the processing graph.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import numpy as np
import sacn
from pydantic import Field

from rasl.config.models import SourceNodeConfig
from rasl.engine.base_node import BaseNode
from rasl.engine.frame import ArrayPayload, Frame
from rasl.engine.node import NodeContext
from rasl.engine.ports import PortGroup, PortSpec
from rasl.engine.registry import node


@node("SacnSourceNode", "SacnSource")
class SacnSourceNode(BaseNode):
    """Source node that receives sACN (E1.31) DMX universe data.

    SacnSourceNode listens on the specified network interface for sACN
    multicast packets and converts incoming DMX data into normalized
    Frames. Each received universe is emitted as a separate Frame with
    the channel data normalized to float32 [0.0, 1.0].

    Example config:
        rasl {
            node SacnSource sacnSource {
                universes 1 2;
                bind_address "0.0.0.0";
                bind_port 5568;
            }
        }
    """

    class Config(SourceNodeConfig):
        """Configuration for SacnSourceNode."""

        universes: list[int] = Field(..., min_length=1, description="Universe numbers to listen to")
        bind_address: str = Field("0.0.0.0", description="Network interface to bind to")
        bind_port: int = Field(5568, ge=1, le=65535, description="UDP port to listen on")

    outputs = PortGroup(dmx=PortSpec(accepts="array"))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._config = config
        self._universes = sorted(set(config.universes))
        self._bind_address = config.bind_address
        self._bind_port = config.bind_port
        self._receiver: Optional[sacn.sACNreceiver] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ctx: Optional[NodeContext] = None

    async def start(self, ctx: NodeContext) -> None:
        self._ctx = ctx
        self._loop = asyncio.get_running_loop()
        self._receiver = sacn.sACNreceiver(
            bind_address=self._bind_address, bind_port=self._bind_port
        )
        self._receiver.start()
        for universe in self._universes:
            self._receiver.register_listener(
                "universe", self._make_listener(universe), universe=universe
            )

    def _make_listener(self, universe: int) -> Any:
        """Create a callback function for a specific universe."""

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
                payload=ArrayPayload(slots),
                metadata={k: v for k, v in metadata.items() if v is not None},
            )
            asyncio.run_coroutine_threadsafe(self._ctx.emit("dmx", frame), self._loop)

        return _listener

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        pass  # Source nodes don't receive frames

    async def stop(self, ctx: NodeContext) -> None:
        if self._receiver is not None:
            self._receiver.stop()
            self._receiver = None
