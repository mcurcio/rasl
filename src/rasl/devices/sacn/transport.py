"""The sACN transports that SacnUniverse nodes share through ``NodeContext.resources``.

- ``CID_KEY``: the runtime's sACN component id (CID), one per runtime, kept across live
  reloads. Senders put it in their packets; receivers drop packets that carry it, so a
  node never hears its own output (owner, 2026-11-20, D9).
- ``SacnReceiver``: one UDP socket per (bind address, port), shared by every universe
  received on it. Its thread only decodes packets and hands them to the event loop;
  sequence, arbitration and the per-universe packet counters live on the loop, so no
  state is shared between threads.

The E1.31 rules themselves (codec, sequence numbers, which source wins) are in
``rasl.devices.sacn.protocol``.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import anyio
import structlog
from sacn.receiving.receiver_socket_udp import ReceiverSocketUDP

from rasl.devices.sacn import protocol
from rasl.graph.node import Lease, ResourceKey, Resources
from rasl.signal import RollingCounter

logger = structlog.get_logger()

CID_KEY: ResourceKey[bytes] = ResourceKey("sacn.cid")
"""The runtime's sACN CID: 16 random bytes (uuid4), opened by the first transport."""


async def acquire_cid(resources: Resources) -> Lease[bytes]:
    """A share of the runtime's CID (``CID_KEY``)."""

    async def _open() -> bytes:
        return uuid.uuid4().bytes

    async def _close(cid: bytes) -> None:
        return None

    return await resources.acquire(CID_KEY, _open, _close)


def receiver_key(bind_address: str, port: int) -> ResourceKey["SacnReceiver"]:
    """The key of the receiver on (``bind_address``, ``port``)."""
    return ResourceKey("sacn.receiver", (bind_address, port))


@dataclass(frozen=True, slots=True)
class UniverseUpdate:
    """What a subscriber of one universe is told, on the event loop.

    Attributes:
        universe: The universe.
        slots: The winning source's DMX slots (start code 0x00 data, not padded), or
            None for a stream termination.
        terminated: True when the winning source ended its stream and no other source
            is live.
        counter: The universe's packet counter after this update: it advances once
            per accepted data packet, identical data included, and not on termination.
        source: The source the update came from.
        sequence: The packet's E1.31 sequence number (0-255).
    """

    universe: int
    slots: Optional[bytes]
    terminated: bool
    counter: RollingCounter
    source: protocol.SourceInfo
    sequence: int


UpdateCallback = Callable[[UniverseUpdate], None]


class Subscription:
    """One subscriber's interest in one universe of a receiver."""

    def __init__(self, receiver: "SacnReceiver", universe: int, callback: UpdateCallback) -> None:
        self._receiver = receiver
        self.universe = universe
        self._callback = callback
        self._closed = False

    def close(self) -> None:
        """Stop receiving updates. The last subscriber of a universe leaves its
        multicast group. Closing twice does nothing."""
        if self._closed:
            return
        self._closed = True
        self._receiver._unsubscribe(self)

    def _deliver(self, update: UniverseUpdate) -> None:
        if not self._closed:
            self._callback(update)


class _Listener:
    """What the receive thread calls: decode, then hand to the loop. Holds no state."""

    def __init__(self, loop: asyncio.AbstractEventLoop, on_frame: Callable[[protocol.DataFrame, float], None]) -> None:
        self._loop = loop
        self._on_frame = on_frame

    def on_data(self, data: object, current_time: float) -> None:
        """Called on the receive thread with one datagram's bytes."""
        try:
            frame = protocol.decode(bytes(data))  # type: ignore[call-overload]
        except Exception:  # never let a hostile packet end the thread
            return
        if frame is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._on_frame, frame, time.monotonic())
        except RuntimeError:
            return  # the loop has closed: rasl is shutting down

    def on_periodic_callback(self, current_time: float) -> None:
        """Called on the receive thread about every 100 ms; nothing to do (expiry is lazy)."""
        return None


class SacnReceiver:
    """One UDP socket on (bind address, port), shared by the universes received on it.

    Created by ``acquire``; use ``subscribe`` and ``Subscription.close`` from the event
    loop only.
    """

    def __init__(self, bind_address: str, port: int, cid: Lease[bytes], loop: asyncio.AbstractEventLoop) -> None:
        self._bind_address = bind_address
        self._port = port
        self._cid = cid
        self._socket: Optional[ReceiverSocketUDP] = None
        self._subscribers: Dict[int, List[Subscription]] = {}
        self._arbiters: Dict[int, protocol.UniverseArbiter] = {}
        self._counters: Dict[int, RollingCounter] = {}
        self._joined: set[int] = set()
        self._listener = _Listener(loop, self._on_frame)

    @classmethod
    async def acquire(cls, resources: Resources, bind_address: str, port: int) -> Lease["SacnReceiver"]:
        """A share of the receiver on (``bind_address``, ``port``), opening it if needed.

        Raises:
            OSError: If the socket cannot be bound.
        """

        async def _open() -> SacnReceiver:
            cid = await acquire_cid(resources)
            receiver = cls(bind_address, port, cid, asyncio.get_running_loop())
            try:
                receiver._start()
            except BaseException:
                await receiver.close()
                raise
            return receiver

        async def _close(receiver: SacnReceiver) -> None:
            await receiver.close()

        return await resources.acquire(receiver_key(bind_address, port), _open, _close)

    def _start(self) -> None:
        self._socket = ReceiverSocketUDP(self._listener, self._bind_address, self._port)
        self._socket.start()
        logger.info("sacn_receiver_started", bind_address=self._bind_address, port=self._port)

    async def close(self) -> None:
        """Leave every multicast group, stop the receive thread, close the socket and
        release the CID."""
        sock = self._socket
        self._socket = None
        if sock is not None:
            for universe in list(self._joined):
                sock.leave_multicast(protocol.multicast_group(universe))
            self._joined.clear()
            await anyio.to_thread.run_sync(sock.stop)
            # The library closes the socket only when its thread had started
            try:
                sock._socket.close()
            except OSError:
                pass
        self._subscribers.clear()
        await self._cid.release()

    def subscribe(self, universe: int, callback: UpdateCallback) -> Subscription:
        """Receive ``universe``: ``callback`` is called on the loop with each update.

        The first subscriber of a universe joins its multicast group (owner, D8). A
        join that fails logs a warning and the universe is received by unicast only
        (owner, Q14). Universe 0 has no group and is unicast only.
        """
        subscription = Subscription(self, universe, callback)
        subscribers = self._subscribers.setdefault(universe, [])
        subscribers.append(subscription)
        if len(subscribers) == 1:
            self._arbiters[universe] = protocol.UniverseArbiter()
            self._counters.setdefault(universe, RollingCounter())
            self._join(universe)
        return subscription

    def _join(self, universe: int) -> None:
        if universe == 0 or self._socket is None:
            return
        try:
            self._socket.join_multicast(protocol.multicast_group(universe))
        except OSError as e:
            logger.warning(
                "sacn_multicast_join_failed",
                universe=universe,
                bind_address=self._bind_address,
                error=str(e),
                note="receiving this universe by unicast only",
            )
            return
        self._joined.add(universe)

    def _unsubscribe(self, subscription: Subscription) -> None:
        subscribers = self._subscribers.get(subscription.universe, [])
        if subscription in subscribers:
            subscribers.remove(subscription)
        if subscribers:
            return
        universe = subscription.universe
        self._subscribers.pop(universe, None)
        self._arbiters.pop(universe, None)
        if universe in self._joined and self._socket is not None:
            self._socket.leave_multicast(protocol.multicast_group(universe))
        self._joined.discard(universe)

    def _on_frame(self, frame: protocol.DataFrame, now: float) -> None:
        """On the loop: arbitrate one decoded packet and tell the universe's subscribers."""
        if self._socket is None or frame.cid == self._cid.value:
            return
        arbiter = self._arbiters.get(frame.universe)
        if arbiter is None:
            return
        verdict = arbiter.accept(frame, now)
        if verdict is protocol.Verdict.IGNORED:
            return
        counter = self._counters[frame.universe]
        if verdict is protocol.Verdict.DATA:
            counter = counter.advanced()
            self._counters[frame.universe] = counter
        update = UniverseUpdate(
            universe=frame.universe,
            slots=frame.slots if verdict is protocol.Verdict.DATA else None,
            terminated=verdict is protocol.Verdict.TERMINATED,
            counter=counter,
            source=protocol.SourceInfo(cid=frame.cid, name=frame.source_name, priority=frame.priority),
            sequence=frame.sequence,
        )
        for subscription in list(self._subscribers.get(frame.universe, [])):
            subscription._deliver(update)
