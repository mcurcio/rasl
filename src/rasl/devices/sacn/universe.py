"""SacnUniverse: one sACN (E1.31) universe in the graph.

Owner, 2026-11-20 (rasl-2lg): sACN packets are per universe, so a node is one universe.
It exposes facts and makes no policy: raw channel values, a packet counter and a
stream-terminated flag. What to do when a stream stops (blank, hold, fall back) is
wiring downstream; grouping channels into pixels is ``Reshape``; merging or splitting
universes is ``connect`` ranges. Its directions follow its wiring: it receives when
any output is connected, and sends when its ``dmx`` input is.
"""

from __future__ import annotations

import time
from fractions import Fraction
from types import MappingProxyType
from typing import Optional, Sequence

import numpy as np
from pydantic import Field, field_validator

from rasl.devices.sacn.transport import SacnOutput, SacnReceiver, Subscription, UniverseUpdate
from rasl.graph import Edge, ExecutionPlan
from rasl.graph.node import BaseNode, Lease, NodeContext, TickContext, TransformNodeConfig, node, pull_rate
from rasl.graph.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.signal import BoolPayload, Frame, MatrixPayload, RollingCounter
from rasl.units import Frequency


@node("SacnUniverseNode", "SacnUniverse")
class SacnUniverseNode(BaseNode):
    """One sACN universe. With its ``dmx`` input connected it sends the universe; with
    any output connected it receives it. Both may be wired at once.

    Sending: ``fps`` times a second it sends the input's latest frame as one data
    packet: values row by row, clipped to 0..1, times 255 (truncated), cut or padded to
    ``channels`` slots. Nothing is sent before the first frame. It goes to the universe's
    multicast group, or to ``target``. With ``sync`` set, the packet asks
    receivers to hold it until the synchronization packet the sender sends for that
    universe after every tick it sent data in; universes sharing a ``sync``
    change together. When no node sends the universe any more, three stream-terminated
    packets are sent (not on a live reload that keeps it).

    Receiving, with any output connected:

    - ``dmx`` (default output): the channel values, ``channels`` rows of 1 column,
      each a DMX slot / 255 (0 to 1). A packet with fewer slots leaves the rest 0.
    - ``count``: a ``RollingCounter`` that advances once per data packet accepted
      from the winning source, identical data included.
    - ``terminated``: true once the winning source ends its stream (and no other
      source is live), false again when data arrives.

    The receiver on (``bind``, ``port``) is shared with every other universe
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

    class Config(TransformNodeConfig):
        """Configuration for SacnUniverseNode."""

        universe: int = Field(..., ge=0, le=63999, description="sACN universe number")
        channels: int = Field(512, ge=1, le=512, description="DMX channels (slots) on the dmx output and in packets sent")
        bind: str = Field(
            "0.0.0.0", description="Local address: the interface multicast groups are joined on, and the one packets are sent from"
        )
        port: int = Field(5568, ge=1, le=65535, description="UDP port to receive on")
        target: Optional[str] = Field(
            None, description="Send to this IP address by unicast; unset sends to the universe's multicast group"
        )
        fps: Frequency = Field(Frequency("40hz"), description="Packets sent per second (1 to 1000)")
        priority: int = Field(100, ge=0, le=200, description="sACN priority of packets sent")
        source_name: str = Field("RASL", description="sACN source name of packets sent (UTF-8, 63 bytes at most)")
        ttl: int = Field(8, ge=1, le=255, description="Time to live of multicast packets sent")
        send_port: int = Field(0, ge=0, le=65535, description="Local UDP port to send from; 0 picks one")
        sync: int = Field(0, ge=0, le=63999, description="Synchronization universe of packets sent; 0 for none")

        @field_validator("source_name")
        @classmethod
        def _name_fits(cls, value: str) -> str:
            if len(value.encode("utf-8")) > 63:
                raise ValueError("source_name must be 63 bytes or fewer in UTF-8")
            return value

        @field_validator("fps")
        @classmethod
        def _fps_in_range(cls, value: Frequency) -> Frequency:
            # At least 1 Hz keeps receivers from timing out (E1.31: 2.5 s); at most
            # 1000 Hz, as every other sink
            if not 1 <= value.hz <= 1000:
                raise ValueError(f"fps must be between 1hz and 1000hz (got {value})")
            return value

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._universe = config.universe
        self._channels = config.channels
        self._bind_address = config.bind
        self._port = config.port
        self._destination = config.target
        self._priority = config.priority
        self._source_name = config.source_name
        self._ttl = config.ttl
        self._send_port = config.send_port
        self._sync_universe = config.sync
        self._fps = config.fps.hz
        self.inputs = PortGroup.inputs(dmx=InputPortSpec(MatrixPayload, description="Values to send"))
        self.outputs = PortGroup.outputs(
            dmx=OutputPortSpec(MatrixPayload, count=config.channels, components=1, pushed=True),
            count=OutputPortSpec(RollingCounter, pushed=True),
            terminated=OutputPortSpec(BoolPayload, count=1, pushed=True),
        ).with_default("dmx")
        self._ctx: Optional[NodeContext] = None
        self._receiver: Optional[Lease[SacnReceiver]] = None
        self._subscription: Optional[Subscription] = None
        self._terminated: Optional[bool] = None
        self._output: Optional[Lease[SacnOutput]] = None

    @property
    def send_target(self) -> tuple[str, int, int, Optional[str]]:
        """Where this node sends: (bind address, send port, universe, destination)."""
        return (self._bind_address, self._send_port, self._universe, self._destination)

    @property
    def send_rate(self) -> float:
        """Packets sent per second when sending."""
        return self._fps

    @property
    def sync_universe(self) -> int:
        """The synchronization universe of packets sent; 0 for none."""
        return self._sync_universe

    def validate_connections(self, incoming_edges: Sequence[Edge]) -> None:
        """Universe 0 has no multicast group, so sending it needs a ``target``.

        Raises:
            ValueError: If the ``dmx`` input is wired, the universe is 0 and no
                ``target`` is set.
        """
        sends = any(edge.target_port == "dmx" for edge in incoming_edges)
        if sends and self._universe == 0 and self._destination is None:
            raise ValueError(
                f"Node '{self.id}': universe 0 has no multicast group; set target to send it"
            )

    @classmethod
    def plan_warnings(cls, plan: ExecutionPlan, node_ids: Sequence[str]) -> list[tuple[str, str, str]]:
        """Warnings about how this plan's SacnUniverse nodes send, as (node id, code, message).

        - Two nodes sending the same universe to the same place: their packets interleave
          (owner, 2026-11-20: a warning, not an error).
        - A synchronization universe whose senders' rates are neither equal nor whole
          multiples of each other: they rarely share a tick, so most synchronization
          packets cover one universe (owner, 2026-11-21).
        """
        senders = [n for n in node_ids if "dmx" in plan.wiring(n).inputs]
        warnings: list[tuple[str, str, str]] = []
        # Keyed on where packets go, not where they leave from: one CID per runtime,
        # so two local sockets sending one universe still interleave at receivers
        by_target: dict[tuple[int, Optional[str]], list[str]] = {}
        for node_id in senders:
            _, _, universe, destination = plan.nodes[node_id].send_target  # type: ignore[attr-defined]
            by_target.setdefault((universe, destination), []).append(node_id)
        for (universe, destination), ids in by_target.items():
            for node_id in ids[1:]:
                where = destination or "its multicast group"
                warnings.append((node_id, "rasl/sacn-duplicate", (
                    f"'{node_id}' and '{ids[0]}' both send universe {universe} to {where}; "
                    "their packets will interleave"
                )))
        by_sync: dict[int, list[str]] = {}
        for node_id in senders:
            sync = plan.nodes[node_id].sync_universe  # type: ignore[attr-defined]
            if sync:
                by_sync.setdefault(sync, []).append(node_id)
        for sync, ids in by_sync.items():
            rates = {n: Fraction(plan.nodes[n].send_rate).limit_denominator(10_000) for n in ids}  # type: ignore[attr-defined]
            fastest = max(rates.values())
            uneven = [n for n, r in rates.items() if (fastest / r).denominator != 1]
            if uneven:
                listed = ", ".join(f"'{n}' at {float(rates[n]):g} Hz" for n in ids)
                warnings.append((uneven[0], "rasl/sacn-sync-rate", (
                    f"sync universe {sync} has senders at rates that rarely share a tick ({listed}); "
                    "use equal rates or whole multiples so they change together"
                )))
        return warnings

    async def start(self, ctx: NodeContext) -> None:
        """Open what the wiring asks for: the shared output when ``dmx`` is an input,
        the shared receiver when an output is connected."""
        self._ctx = ctx
        sends = "dmx" in ctx.wiring.inputs
        receives = bool(ctx.wiring.outputs)
        if not (sends or receives):
            ctx.logger.info("sacn_universe_unwired", universe=self._universe)
            return
        try:
            if sends:
                self._output = await SacnOutput.acquire(
                    ctx.resources, self._bind_address, self._send_port, self._universe, self._destination
                )
            if receives:
                self._receiver = await SacnReceiver.acquire(ctx.resources, self._bind_address, self._port)
                self._subscription = self._receiver.value.subscribe(self._universe, self._on_update)
        except BaseException:
            # Half started is not started: give back what was acquired
            await self.stop(ctx)
            raise

    @pull_rate(lambda self, wiring: self._fps if "dmx" in wiring.inputs else None, wiring=True)
    async def pull(self, tick: TickContext) -> None:
        """Send the ``dmx`` input's latest frame as one data packet, when sending.

        Raises:
            OSError: If the packet cannot be sent (a full buffer only drops it).
        """
        if self._output is None:
            return
        frame = self.inputs.dmx.read()
        if frame is None:
            return
        values = np.asarray(frame.payload, dtype=np.float32).reshape(-1)[: self._channels]
        slots = np.zeros(self._channels, dtype=np.uint8)
        slots[: len(values)] = (np.clip(values, 0.0, 1.0) * 255.0).astype(np.uint8)
        self._output.value.send(
            slots.tobytes(),
            priority=self._priority,
            source_name=self._source_name,
            ttl=self._ttl,
            sync_universe=self._sync_universe,
        )

    async def stop(self, ctx: NodeContext) -> None:
        """Stop receiving and give up the shared receiver and output."""
        try:
            if self._subscription is not None:
                self._subscription.close()
        finally:
            self._subscription = None
            leases = (self._receiver, self._output)
            self._receiver = self._output = None
            for lease in leases:
                if lease is not None:
                    await lease.release()

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
