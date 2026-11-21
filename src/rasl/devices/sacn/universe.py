"""SacnUniverse: one sACN (E1.31) universe in the graph.

Owner, 2026-11-20 (rasl-2lg): sACN packets are per universe, so a node is one universe.
It exposes facts and makes no policy: raw channel values, a packet counter and a
stream-terminated flag. What to do when a stream stops (blank, hold, fall back) is
wiring downstream; grouping channels into pixels is ``Reshape``; merging or splitting
universes is ``connect`` ranges. Its directions follow its wiring: it receives when
any output is connected.
"""

from __future__ import annotations

import time
from types import MappingProxyType
from typing import Optional

import numpy as np
from pydantic import Field

from rasl.devices.sacn.transport import SacnReceiver, Subscription, UniverseUpdate
from rasl.graph.node import BaseNode, Lease, NodeContext, TickContext, TransformNodeConfig, node
from rasl.graph.ports import EMPTY_PORTS, OutputPortSpec, PortGroup
from rasl.signal import BoolPayload, Frame, MatrixPayload, RollingCounter


@node("SacnUniverseNode", "SacnUniverse")
class SacnUniverseNode(BaseNode):
    """One sACN universe. With any output connected it receives the universe:

    - ``dmx`` (default output): the channel values, ``channels`` rows of 1 column,
      each a DMX slot / 255 (0 to 1). A packet with fewer slots leaves the rest 0.
    - ``count``: a ``RollingCounter`` that advances once per data packet accepted
      from the winning source, identical data included.
    - ``terminated``: true once the winning source ends its stream (and no other
      source is live), false again when data arrives.

    The receiver on (``bind_address``, ``port``) is shared with every other universe
    received there; it joins the universe's multicast group and takes unicast too.
    Of several sources on one universe, the highest priority wins; at equal priority
    the first seen holds it until it stops or is silent for 2.5 s.

    Example config:
        graph {
            node SacnUniverse hyperhdr { universe 1; channels 432; }
            node Reshape pixels { components 3; connect hyperhdr; }
        }
    """

    restart_on_wiring_change = True
    inputs = EMPTY_PORTS

    class Config(TransformNodeConfig):
        """Configuration for SacnUniverseNode."""

        universe: int = Field(..., ge=0, le=63999, description="sACN universe number")
        channels: int = Field(512, ge=1, le=512, description="DMX channels (slots) on the dmx output")
        bind_address: str = Field(
            "0.0.0.0", description="Interface to receive on (and to join multicast groups on)"
        )
        port: int = Field(5568, ge=1, le=65535, description="UDP port to receive on")

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._universe = config.universe
        self._channels = config.channels
        self._bind_address = config.bind_address
        self._port = config.port
        self.outputs = PortGroup.outputs(
            dmx=OutputPortSpec(MatrixPayload, count=config.channels, components=1),
            count=OutputPortSpec(RollingCounter),
            terminated=OutputPortSpec(BoolPayload, count=1),
        ).with_default("dmx")
        self._ctx: Optional[NodeContext] = None
        self._receiver: Optional[Lease[SacnReceiver]] = None
        self._subscription: Optional[Subscription] = None
        self._terminated: Optional[bool] = None

    async def start(self, ctx: NodeContext) -> None:
        """Open what the wiring asks for: the shared receiver when an output is connected."""
        self._ctx = ctx
        if not ctx.wiring.outputs:
            ctx.logger.info("sacn_universe_unwired", universe=self._universe)
            return
        self._receiver = await SacnReceiver.acquire(ctx.resources, self._bind_address, self._port)
        self._subscription = self._receiver.value.subscribe(self._universe, self._on_update)

    async def pull(self, tick: TickContext) -> None:
        """Nothing to do: received frames arrive between ticks."""
        return None

    async def stop(self, ctx: NodeContext) -> None:
        """Stop receiving and give up the shared receiver."""
        try:
            if self._subscription is not None:
                self._subscription.close()
        finally:
            self._subscription = None
            receiver, self._receiver = self._receiver, None
            if receiver is not None:
                await receiver.release()

    def _on_update(self, update: UniverseUpdate) -> None:
        """On the loop: write what the receiver accepted to the outputs."""
        ctx = self._ctx
        if ctx is None or self._subscription is None:
            return
        now = time.monotonic()
        metadata = MappingProxyType(
            {
                "sourceCid": update.source.cid.hex(),
                "sourceName": update.source.name,
                "priority": update.source.priority,
                "sequence": update.sequence,
                **self._metadata,
            }
        )
        topic = f"sacn.universe.{self._universe}"

        def emit(port: str, payload: object) -> None:
            ctx.inject(port, Frame(topic=topic, timestamp=now, payload=payload, metadata=metadata))

        if update.terminated:
            self._terminated = True
            emit("terminated", BoolPayload(np.ones(1, dtype=np.float32)))
            return
        assert update.slots is not None
        values = np.zeros((self._channels, 1), dtype=np.float32)
        slots = np.frombuffer(update.slots, dtype=np.uint8)[: self._channels]
        values[: len(slots), 0] = slots / np.float32(255.0)
        emit("count", update.counter)
        emit("dmx", MatrixPayload(values))
        if self._terminated is not False:
            self._terminated = False
            emit("terminated", BoolPayload(np.zeros(1, dtype=np.float32)))
