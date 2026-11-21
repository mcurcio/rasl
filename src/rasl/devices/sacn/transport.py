"""The sACN transports that SacnUniverse nodes share through ``NodeContext.resources``.

- ``CID_KEY``: the runtime's sACN component id (CID), one per runtime, kept across live
  reloads. Senders put it in their packets; receivers drop packets that carry it, so a
  node never hears its own output (owner, 2026-11-20, D9).
- ``SacnReceiver``: one UDP socket per (bind address, port), shared by every universe
  received on it. Its thread only decodes packets and hands them to the event loop;
  sequence, arbitration and the per-universe packet counters live on the loop, so no
  state is shared between threads. Data that names a synchronization universe is held
  until that source's synchronization packet releases it (see ``SacnReceiver``).
- ``SacnSender``: one non-blocking UDP socket per (bind address, send port). No thread
  and no clock: a node sends its universe's packet in its own pull, and at the end of
  the tick (``EndOfTick``) the sender sends one synchronization packet per
  synchronization universe that sent data in it (owner, 2026-11-21).
- ``SacnOutput``: one universe (and destination) on a sender: its sequence numbers, and
  the stream-terminated packets sent when the last node sending it is gone. A reload that
  restarts the node keeps it (the registry defers the close), so no termination is sent.

The E1.31 rules themselves (codec, sequence numbers, which source wins) are in
``rasl.devices.sacn.protocol``.
"""

from __future__ import annotations

import asyncio
import socket
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import anyio
import structlog
from sacn.receiving.receiver_socket_udp import ReceiverSocketUDP

from rasl.devices.sacn import protocol
from rasl.graph.node import Lease, ResourceKey, Resources, TickContext
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


def sender_key(bind_address: str, send_port: int) -> ResourceKey["SacnSender"]:
    """The key of the sender on (``bind_address``, ``send_port``)."""
    return ResourceKey("sacn.sender", (bind_address, send_port))


def output_key(
    bind_address: str, send_port: int, universe: int, destination: Optional[str]
) -> ResourceKey["SacnOutput"]:
    """The key of one universe sent to ``destination`` (None: its multicast group)."""
    return ResourceKey("sacn.output", (bind_address, send_port, universe, destination))


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

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        on_frame: Callable[[protocol.DataFrame | protocol.SyncFrame, float], None],
    ) -> None:
        self._loop = loop
        self._on_frame = on_frame

    def on_data(self, data: object, current_time: float) -> None:
        """Called on the receive thread with one datagram's bytes."""
        try:
            raw = bytes(data)  # type: ignore[call-overload]
            frame: protocol.DataFrame | protocol.SyncFrame | None = protocol.decode(raw)
            if frame is None:
                frame = protocol.decode_sync(raw)
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

    Synchronization (E1.31 6.6, 11; owner, 2026-11-21): accepted data that names a
    synchronization universe is held, newest per universe, while that source has sent a
    synchronization packet for it within the last 2.5 s; the source's next
    synchronization packet releases everything held for it at once. Without a recent
    synchronization packet (none yet, or the source stopped sending them) data is
    delivered at once. The packet counter advances when data is accepted, and subscribers
    see it with the released data. The receiver joins a synchronization universe's
    multicast group the first time data names it, and leaves at close.

    A universe whose last subscriber leaves keeps its multicast group, its source
    arbitration and its counter until the end of the tick (``EndOfTick``), so a live
    reload that restarts its node (between ticks) keeps them.
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
        self._sync_joined: set[int] = set()
        self._sync_join_failed: set[int] = set()
        self._last_sync: Dict[tuple[bytes, int], float] = {}
        self._sync_sequences: Dict[int, protocol.SequenceTracker] = {}
        self._held: Dict[tuple[bytes, int], Dict[int, UniverseUpdate]] = {}
        self._idle: set[int] = set()
        """Universes whose last subscriber left; dropped at the end of the tick."""
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
            for universe in self._joined | self._sync_joined:
                sock.leave_multicast(protocol.multicast_group(universe))
            self._joined.clear()
            self._sync_joined.clear()
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
        self._idle.discard(universe)
        if universe not in self._arbiters:
            self._arbiters[universe] = protocol.UniverseArbiter()
            self._counters.setdefault(universe, RollingCounter())
            self._join(universe)
        return subscription

    def _join(self, universe: int) -> None:
        if universe == 0 or self._socket is None or universe in self._sync_joined:
            if universe in self._sync_joined:
                self._joined.add(universe)
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
        # Kept until the end of the tick: a live reload's swap (between ticks) that
        # restarts the node subscribes again before then, and keeps the group and
        # the source arbitration (end_tick)
        self._subscribers.pop(subscription.universe, None)
        self._idle.add(subscription.universe)

    def end_tick(self, tick: TickContext) -> None:
        """Leave the groups of universes nobody subscribed to again since the last
        tick (``EndOfTick``), and forget their arbitration."""
        for universe in list(self._idle):
            self._drop_universe(universe)
        self._idle.clear()

    def _drop_universe(self, universe: int) -> None:
        self._arbiters.pop(universe, None)
        if universe in self._joined and universe not in self._sync_joined and self._socket is not None:
            self._socket.leave_multicast(protocol.multicast_group(universe))
        self._joined.discard(universe)
        for held in self._held.values():
            held.pop(universe, None)

    def _on_frame(self, frame: protocol.DataFrame | protocol.SyncFrame, now: float) -> None:
        """On the loop: handle one decoded packet."""
        if self._socket is None or frame.cid == self._cid.value:
            return
        if isinstance(frame, protocol.SyncFrame):
            self._on_sync(frame, now)
        else:
            self._on_data(frame, now)

    def _on_data(self, frame: protocol.DataFrame, now: float) -> None:
        """Arbitrate one data packet; deliver it, or hold it for its synchronization."""
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
        if verdict is protocol.Verdict.TERMINATED:
            for held in self._held.values():
                held.pop(frame.universe, None)
        elif frame.sync_address:
            key = (frame.cid, frame.sync_address)
            self._join_sync(frame.sync_address)
            last = self._last_sync.get(key)
            if last is not None and now - last <= protocol.LOSS_TIMEOUT_S:
                self._held.setdefault(key, {})[frame.universe] = update
                return
            # Synchronization stopped: what was held goes out now, then data as it comes
            for held in self._held.pop(key, {}).values():
                if held.universe != frame.universe:
                    self._deliver(held)
        self._deliver(update)

    def _on_sync(self, frame: protocol.SyncFrame, now: float) -> None:
        """Release what a source held for this synchronization universe."""
        tracker = self._sync_sequences.setdefault(frame.sync_universe, protocol.SequenceTracker())
        if not tracker.accept(frame.cid, frame.sequence):
            return
        key = (frame.cid, frame.sync_universe)
        self._last_sync[key] = now
        for update in self._held.pop(key, {}).values():
            self._deliver(update)

    def _join_sync(self, sync_universe: int) -> None:
        if (
            sync_universe in self._sync_joined
            or sync_universe in self._sync_join_failed
            or self._socket is None
        ):
            return
        if sync_universe in self._joined:
            self._sync_joined.add(sync_universe)  # already a member for its data
            return
        try:
            self._socket.join_multicast(protocol.multicast_group(sync_universe))
        except OSError as e:
            # Not retried for every packet; a data subscription to it still tries
            self._sync_join_failed.add(sync_universe)
            logger.warning(
                "sacn_multicast_join_failed",
                universe=sync_universe,
                bind_address=self._bind_address,
                error=str(e),
                note="synchronization packets for it arrive by unicast only",
            )
            return
        self._sync_joined.add(sync_universe)

    def _deliver(self, update: UniverseUpdate) -> None:
        for subscription in list(self._subscribers.get(update.universe, [])):
            subscription._deliver(update)


class SacnSender:
    """One non-blocking UDP socket that sends sACN under the runtime's CID.

    Loop thread only. Created by ``acquire``. Implements ``EndOfTick``: after a tick's
    pulls it sends one synchronization packet per synchronization universe that data
    was sent for in that tick, to its multicast group or, for data sent by unicast, to
    each destination (owner, 2026-11-21).
    """

    def __init__(self, bind_address: str, send_port: int, cid: Lease[bytes]) -> None:
        self._bind_address = bind_address
        self._send_port = send_port
        self._cid = cid
        self._socket: Optional[socket.socket] = None
        self._ttl: Optional[int] = None
        self._pending_sync: Dict[tuple[int, Optional[str]], int] = {}
        self._sync_sequence: Dict[int, int] = {}
        self.dropped = 0
        """Packets dropped because the socket's send buffer was full."""

    @classmethod
    async def acquire(cls, resources: Resources, bind_address: str, send_port: int) -> Lease["SacnSender"]:
        """A share of the sender on (``bind_address``, ``send_port``), opening it if needed.

        Raises:
            OSError: If the socket cannot be bound.
        """

        async def _open() -> SacnSender:
            cid = await acquire_cid(resources)
            sender = cls(bind_address, send_port, cid)
            try:
                sender._open_socket()
            except BaseException:
                await sender.close()
                raise
            return sender

        async def _close(sender: SacnSender) -> None:
            await sender.close()

        return await resources.acquire(sender_key(bind_address, send_port), _open, _close)

    @property
    def cid(self) -> bytes:
        """The CID this sender's packets carry."""
        return self._cid.value

    def _open_socket(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            if self._send_port:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self._bind_address, self._send_port))
            if self._bind_address != "0.0.0.0":
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(self._bind_address))
            sock.setblocking(False)
        except BaseException:
            sock.close()
            raise
        self._socket = sock

    async def close(self) -> None:
        """Close the socket (if it opened) and release the CID. Closing twice does nothing."""
        sock, self._socket = self._socket, None
        if sock is not None:
            sock.close()
        await self._cid.release()  # a lease releases once, whatever is called after

    def sendto(self, packet: bytes, universe: int, destination: Optional[str], ttl: int) -> None:
        """Send one packet now, to ``destination`` or else ``universe``'s multicast group.

        A full send buffer drops the packet (counted in ``dropped``).

        Raises:
            OSError: For any other send failure (the node's pull fails).
            ValueError: If ``destination`` is None and ``universe`` has no group (0).
        """
        if self._socket is None:
            raise OSError("sACN sender is closed")
        address = destination if destination is not None else protocol.multicast_group(universe)
        if destination is None and ttl != self._ttl:
            self._socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
            self._ttl = ttl
        try:
            self._socket.sendto(packet, (address, protocol.E131_PORT))
        except BlockingIOError:
            self.dropped += 1

    def note_sync(self, sync_universe: int, destination: Optional[str], ttl: int) -> None:
        """Ask for a synchronization packet for ``sync_universe`` at the end of this tick."""
        key = (sync_universe, destination)
        self._pending_sync[key] = max(ttl, self._pending_sync.get(key, 0))

    def end_tick(self, tick: TickContext) -> None:
        """Send the synchronization packets this tick's data asked for (``EndOfTick``).

        Each synchronization universe's sequence number advances once per tick, whatever
        the number of destinations.

        Raises:
            OSError: If a send fails; the remaining packets are still sent first.
        """
        pending, self._pending_sync = self._pending_sync, {}
        if not pending or self._socket is None:
            return
        packets: Dict[int, bytes] = {}
        error: Optional[OSError] = None
        for (sync_universe, destination), ttl in pending.items():
            if sync_universe not in packets:
                sequence = self._sync_sequence.get(sync_universe, 0)
                self._sync_sequence[sync_universe] = (sequence + 1) % 256
                packets[sync_universe] = protocol.encode_sync(self.cid, sync_universe, sequence)
            try:
                self.sendto(packets[sync_universe], sync_universe, destination, ttl)
            except OSError as e:
                error = error or e
        if error is not None:
            raise error


async def _resolve(host: str) -> str:
    """``host`` as an IPv4 address, looked up once (not on every packet).

    Raises:
        OSError: If it cannot be resolved; the message names it.
    """
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, protocol.E131_PORT, family=socket.AF_INET, type=socket.SOCK_DGRAM)
    except OSError as e:
        raise OSError(f"sACN target {host!r} cannot be resolved: {e}") from e
    return str(infos[0][4][0])


class SacnOutput:
    """One universe sent to one destination through a shared sender.

    Holds the universe's sequence number and what it last sent. Created by ``acquire``;
    closing it (when no node sends this universe any more, after a reload's swap) sends
    three stream-terminated packets (E1.31 6.2.6) if it ever sent data.
    """

    TERMINATION_PACKETS = 3

    def __init__(self, sender: Lease[SacnSender], universe: int, destination: Optional[str]) -> None:
        self._sender = sender
        self.universe = universe
        self.destination = destination
        self._sequence = 0
        self._last: Optional[tuple[bytes, int, str, int, int]] = None
        self._address: Optional[str] = destination
        """``destination`` resolved to an IPv4 address once, when the output opened."""

    @classmethod
    async def acquire(
        cls,
        resources: Resources,
        bind_address: str,
        send_port: int,
        universe: int,
        destination: Optional[str],
    ) -> Lease["SacnOutput"]:
        """A share of ``universe`` sent to ``destination`` on the sender for
        (``bind_address``, ``send_port``), opening both if needed."""

        async def _open() -> SacnOutput:
            address = await _resolve(destination) if destination is not None else None
            sender = await SacnSender.acquire(resources, bind_address, send_port)
            output = cls(sender, universe, destination)
            output._address = address
            return output

        async def _close(output: SacnOutput) -> None:
            await output.close()

        key = output_key(bind_address, send_port, universe, destination)
        return await resources.acquire(key, _open, _close)

    def _next_sequence(self) -> int:
        sequence = self._sequence
        self._sequence = (sequence + 1) % 256
        return sequence

    def send(
        self, slots: bytes, *, priority: int, source_name: str, ttl: int, sync_universe: int = 0
    ) -> None:
        """Send one data packet now; with ``sync_universe``, ask the sender for that
        universe's synchronization packet at the end of the tick.

        Raises:
            OSError: If the send fails (other than a full buffer).
            ValueError: If an argument is out of range (see ``protocol.encode_data``).
        """
        sender = self._sender.value
        packet = protocol.encode_data(
            sender.cid, self.universe, self._next_sequence(), priority, source_name, slots,
            sync_address=sync_universe,
        )
        self._last = (slots, priority, source_name, ttl, sync_universe)
        sender.sendto(packet, self.universe, self._address, ttl)
        if sync_universe:
            sender.note_sync(sync_universe, self._address, ttl)

    def terminate(self) -> None:
        """Send the stream-terminated packets, if this output ever sent data; errors are
        logged, not raised."""
        if self._last is None:
            return
        slots, priority, source_name, ttl, sync_universe = self._last
        sender = self._sender.value
        try:
            for _ in range(self.TERMINATION_PACKETS):
                packet = protocol.encode_data(
                    sender.cid, self.universe, self._next_sequence(), priority, source_name, slots,
                    terminated=True, sync_address=sync_universe,
                )
                sender.sendto(packet, self.universe, self._address, ttl)
        except OSError as e:
            logger.warning("sacn_termination_failed", universe=self.universe, error=str(e))
        self._last = None

    async def close(self) -> None:
        """Terminate the stream and release the sender."""
        try:
            self.terminate()
        finally:
            await self._sender.release()
