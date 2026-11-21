"""SacnReceiver: one socket per (address, port), decoded on its thread, arbitrated on the loop."""

from __future__ import annotations

import asyncio
import socket
import threading

import anyio
import pytest

from rasl.devices.sacn import protocol
from rasl.devices.sacn.transport import CID_KEY, SacnReceiver, UniverseUpdate
from rasl.runtime.resources import ResourceRegistry

OTHER_CID = bytes(range(16))


def packet(universe: int, sequence: int, slots: bytes = b"\x10\x20\x30", *, cid: bytes = OTHER_CID,
           priority: int = 100, terminated: bool = False) -> bytes:
    """One E1.31 data packet."""
    return protocol.encode_data(cid, universe, sequence, priority, "test", slots, terminated=terminated)


def port_of(receiver: SacnReceiver) -> int:
    """The UDP port the receiver's socket is bound to."""
    return receiver._socket._socket.getsockname()[1]


async def until(condition, timeout: float = 2.0) -> None:
    """Wait for ``condition()`` to hold."""
    with anyio.fail_after(timeout):
        while not condition():
            await anyio.sleep(0.005)


@pytest.fixture
async def registry():
    registry = ResourceRegistry()
    yield registry
    await registry.close_all()


async def test_receivers_on_one_address_and_port_are_one_socket(registry: ResourceRegistry) -> None:
    first = await SacnReceiver.acquire(registry, "127.0.0.1", 0)
    second = await SacnReceiver.acquire(registry, "127.0.0.1", 0)
    assert second.value is first.value
    third = await SacnReceiver.acquire(registry, "127.0.0.2", 0)
    assert third.value is not first.value


async def test_packets_sent_over_udp_reach_subscribers_on_the_loop_thread(registry: ResourceRegistry) -> None:
    lease = await SacnReceiver.acquire(registry, "127.0.0.1", 0)
    got: list[tuple[UniverseUpdate, int]] = []
    lease.value.subscribe(7, lambda u: got.append((u, threading.get_ident())))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tx:
        tx.sendto(packet(7, 1), ("127.0.0.1", port_of(lease.value)))
        tx.sendto(packet(8, 1), ("127.0.0.1", port_of(lease.value)))  # nobody subscribed
        await until(lambda: got)
    update, thread = got[0]
    assert thread == threading.get_ident()
    assert update.universe == 7
    assert update.slots == b"\x10\x20\x30"
    assert update.counter.value == 1
    assert update.source.cid == OTHER_CID
    await anyio.sleep(0.05)
    assert len(got) == 1


async def test_identical_packets_each_advance_the_counter(registry: ResourceRegistry) -> None:
    """Owner, Q5: the counter advances per packet accepted, data unchanged or not."""
    lease = await SacnReceiver.acquire(registry, "127.0.0.1", 0)
    receiver = lease.value
    got: list[UniverseUpdate] = []
    receiver.subscribe(1, got.append)
    for sequence in range(3):
        receiver._listener.on_data(packet(1, sequence), 0.0)
    await until(lambda: len(got) == 3)
    assert [u.counter.value for u in got] == [1, 2, 3]


async def test_a_stream_termination_is_reported_once_and_does_not_advance_the_counter(
    registry: ResourceRegistry,
) -> None:
    lease = await SacnReceiver.acquire(registry, "127.0.0.1", 0)
    receiver = lease.value
    got: list[UniverseUpdate] = []
    receiver.subscribe(1, got.append)
    receiver._listener.on_data(packet(1, 0), 0.0)
    for sequence in (1, 2, 3):  # senders send three
        receiver._listener.on_data(packet(1, sequence, terminated=True), 0.0)
    await until(lambda: len(got) >= 2)
    await anyio.sleep(0.02)
    assert [(u.terminated, u.slots, u.counter.value) for u in got] == [
        (False, b"\x10\x20\x30", 1),
        (True, None, 1),
    ]


async def test_packets_carrying_the_runtimes_own_cid_are_dropped(registry: ResourceRegistry) -> None:
    lease = await SacnReceiver.acquire(registry, "127.0.0.1", 0)
    receiver = lease.value
    own_cid = receiver._cid.value
    got: list[UniverseUpdate] = []
    receiver.subscribe(1, got.append)
    receiver._listener.on_data(packet(1, 0, cid=own_cid), 0.0)
    receiver._listener.on_data(packet(1, 0), 0.0)
    await until(lambda: got)
    await anyio.sleep(0.02)
    assert [u.source.cid for u in got] == [OTHER_CID]


async def test_the_cid_is_one_per_runtime(registry: ResourceRegistry) -> None:
    a = await SacnReceiver.acquire(registry, "127.0.0.1", 0)
    b = await SacnReceiver.acquire(registry, "127.0.0.2", 0)
    assert a.value._cid.value == b.value._cid.value
    assert len(a.value._cid.value) == 16
    assert CID_KEY in registry._entries


async def test_the_first_subscriber_joins_the_group_and_the_last_leaves(registry: ResourceRegistry) -> None:
    lease = await SacnReceiver.acquire(registry, "127.0.0.1", 0)
    receiver = lease.value
    calls: list[str] = []
    receiver._socket.join_multicast = lambda group: calls.append(f"join {group}")
    receiver._socket.leave_multicast = lambda group: calls.append(f"leave {group}")
    a = receiver.subscribe(258, lambda u: None)
    b = receiver.subscribe(258, lambda u: None)
    zero = receiver.subscribe(0, lambda u: None)  # universe 0 has no group
    a.close()
    a.close()
    assert calls == ["join 239.255.1.2"]
    b.close()
    zero.close()
    assert calls == ["join 239.255.1.2", "leave 239.255.1.2"]


async def test_a_failed_join_warns_and_unicast_still_arrives(registry: ResourceRegistry) -> None:
    """Owner, Q14."""
    lease = await SacnReceiver.acquire(registry, "127.0.0.1", 0)
    receiver = lease.value

    def refuse(group: str) -> None:
        raise OSError("No such device")

    receiver._socket.join_multicast = refuse
    got: list[UniverseUpdate] = []
    receiver.subscribe(3, got.append)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tx:
        tx.sendto(packet(3, 1), ("127.0.0.1", port_of(receiver)))
        await until(lambda: got)


async def test_hostile_packets_do_not_end_the_receive_thread(registry: ResourceRegistry) -> None:
    lease = await SacnReceiver.acquire(registry, "127.0.0.1", 0)
    receiver = lease.value
    got: list[UniverseUpdate] = []
    receiver.subscribe(1, got.append)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tx:
        for junk in (b"", b"\x00" * 10, b"\xff" * 700, packet(1, 1)[:60]):
            tx.sendto(junk, ("127.0.0.1", port_of(receiver)))
        tx.sendto(packet(1, 1), ("127.0.0.1", port_of(receiver)))
        await until(lambda: got)
    assert receiver._socket._thread.is_alive()


async def test_a_closed_loop_does_not_raise_on_the_receive_thread() -> None:
    from rasl.devices.sacn.transport import _Listener

    loop = asyncio.new_event_loop()
    loop.close()
    listener = _Listener(loop, lambda frame, now: None)
    listener.on_data(packet(1, 1), 0.0)  # nothing raised


async def test_closing_stops_the_thread_and_closes_the_socket(registry: ResourceRegistry) -> None:
    lease = await SacnReceiver.acquire(registry, "127.0.0.1", 0)
    sock = lease.value._socket
    await lease.release()
    assert not sock._thread.is_alive()
    assert sock._socket.fileno() == -1


# ---- sending -------------------------------------------------------------------------

from rasl.devices.sacn.transport import SacnOutput  # noqa: E402


class FakeSocket:
    """Records what a sender sends; can be told to fail."""

    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.options: list[tuple[int, int, object]] = []
        self.fail: Exception | None = None

    def sendto(self, packet: bytes, address: tuple[str, int]) -> None:
        if self.fail is not None:
            raise self.fail
        self.sent.append((packet, address))

    def setsockopt(self, level: int, option: int, value: object) -> None:
        self.options.append((level, option, value))

    def close(self) -> None:
        pass


async def fake_output(registry, universe=1, destination=None, port=0):
    lease = await SacnOutput.acquire(registry, "127.0.0.1", port, universe, destination)
    sender = lease.value._sender.value
    real, sender._socket = sender._socket, FakeSocket()
    real.close()
    return lease, sender._socket


async def test_outputs_on_one_address_share_one_sender_and_one_cid(registry: ResourceRegistry) -> None:
    a, _ = await fake_output(registry, 1)
    b = await SacnOutput.acquire(registry, "127.0.0.1", 0, 2, None)
    assert a.value._sender.value is b.value._sender.value
    receiver = await SacnReceiver.acquire(registry, "127.0.0.1", 0)
    assert receiver.value._cid.value == a.value._sender.value.cid


async def test_send_goes_to_the_universes_group_or_the_destination(registry: ResourceRegistry) -> None:
    multicast, sock = await fake_output(registry, 258)
    multicast.value.send(b"\x01\x02", priority=100, source_name="rasl", ttl=8)
    unicast = await SacnOutput.acquire(registry, "127.0.0.1", 0, 0, "10.0.60.30")
    unicast.value.send(b"\x03", priority=100, source_name="rasl", ttl=8)
    assert [address for _, address in sock.sent] == [("239.255.1.2", 5568), ("10.0.60.30", 5568)]
    frame = protocol.decode(sock.sent[0][0])
    assert (frame.universe, frame.slots, frame.sync_address) == (258, b"\x01\x02", 0)


async def test_sequence_numbers_count_per_output_and_wrap(registry: ResourceRegistry) -> None:
    lease, sock = await fake_output(registry, 1)
    output = lease.value
    output._sequence = 254
    for _ in range(3):
        output.send(b"\x00", priority=100, source_name="x", ttl=8)
    assert [protocol.decode(p).sequence for p, _ in sock.sent] == [254, 255, 0]


async def test_a_full_buffer_drops_the_packet_and_other_errors_raise(registry: ResourceRegistry) -> None:
    lease, sock = await fake_output(registry, 1)
    sock.fail = BlockingIOError()
    lease.value.send(b"\x00", priority=100, source_name="x", ttl=8)
    assert lease.value._sender.value.dropped == 1
    sock.fail = OSError("Network is unreachable")
    with pytest.raises(OSError):
        lease.value.send(b"\x00", priority=100, source_name="x", ttl=8)


async def test_closing_an_output_sends_three_terminated_packets_once(registry: ResourceRegistry) -> None:
    lease, sock = await fake_output(registry, 1)
    lease.value.send(b"\x05", priority=120, source_name="x", ttl=8)
    await lease.release()
    frames = [protocol.decode(p) for p, _ in sock.sent]
    assert [f.terminated for f in frames] == [False, True, True, True]
    assert [f.sequence for f in frames] == [0, 1, 2, 3]
    assert frames[-1].priority == 120


async def test_an_output_that_never_sent_terminates_nothing(registry: ResourceRegistry) -> None:
    lease, sock = await fake_output(registry, 1)
    await lease.release()
    assert sock.sent == []


async def test_a_reload_that_keeps_the_universe_sends_no_termination(registry: ResourceRegistry) -> None:
    lease, sock = await fake_output(registry, 1)
    lease.value.send(b"\x05", priority=100, source_name="x", ttl=8)
    async with registry.deferring_close():
        await lease.release()  # the old node stops...
        lease = await SacnOutput.acquire(registry, "127.0.0.1", 0, 1, None)  # ...its successor starts
    lease.value.send(b"\x06", priority=100, source_name="x", ttl=8)
    frames = [protocol.decode(p) for p, _ in sock.sent]
    assert [(f.terminated, f.sequence) for f in frames] == [(False, 0), (False, 1)]


async def test_end_of_tick_sends_one_sync_per_sync_universe_and_destination(registry: ResourceRegistry) -> None:
    a, sock = await fake_output(registry, 1)
    b = await SacnOutput.acquire(registry, "127.0.0.1", 0, 2, None)
    c = await SacnOutput.acquire(registry, "127.0.0.1", 0, 3, "10.0.0.9")
    sender = a.value._sender.value
    for output in (a.value, b.value, c.value):
        output.send(b"\x01", priority=100, source_name="x", ttl=8, sync_universe=500)
    sock.sent.clear()
    sender.end_tick(None)
    syncs = [(protocol.decode_sync(p), address) for p, address in sock.sent]
    assert [address for _, address in syncs] == [("239.255.1.244", 5568), ("10.0.0.9", 5568)]
    assert {frame.sync_universe for frame, _ in syncs} == {500}
    assert {frame.sequence for frame, _ in syncs} == {0}  # once per tick, whatever the destinations
    sock.sent.clear()
    sender.end_tick(None)
    assert sock.sent == []  # nothing sent this tick, nothing to synchronize
    a.value.send(b"\x01", priority=100, source_name="x", ttl=8, sync_universe=500)
    sender.end_tick(None)
    assert protocol.decode_sync(sock.sent[-1][0]).sequence == 1


async def test_data_without_a_sync_universe_asks_for_no_sync(registry: ResourceRegistry) -> None:
    a, sock = await fake_output(registry, 1)
    a.value.send(b"\x01", priority=100, source_name="x", ttl=8)
    sock.sent.clear()
    a.value._sender.value.end_tick(None)
    assert sock.sent == []


async def test_real_packets_reach_a_receiver_over_loopback(registry: ResourceRegistry) -> None:
    """End to end, unicast: the sender's packets decode at a socket on 5568."""
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        rx.bind(("127.0.0.1", 5568))
    except OSError:
        rx.close()
        pytest.skip("port 5568 is in use")
    rx.settimeout(2)
    try:
        lease = await SacnOutput.acquire(registry, "127.0.0.1", 0, 9, "127.0.0.1")
        lease.value.send(b"\x07\x08", priority=100, source_name="x", ttl=8)
        frame = protocol.decode(rx.recv(2048))
        assert (frame.universe, frame.slots) == (9, b"\x07\x08")
    finally:
        rx.close()


# ---- receiving with synchronization ----------------------------------------------------

def synced(universe: int, sequence: int, slots: bytes, sync: int = 500) -> bytes:
    return protocol.encode_data(OTHER_CID, universe, sequence, 100, "src", slots, sync_address=sync)


async def test_data_is_delivered_at_once_until_the_source_sends_sync(registry: ResourceRegistry) -> None:
    lease = await SacnReceiver.acquire(registry, "127.0.0.1", 0)
    receiver = lease.value
    got: list[UniverseUpdate] = []
    receiver.subscribe(1, got.append)
    receiver._on_frame(protocol.decode(synced(1, 0, b"\x01")), 0.0)
    assert [u.slots for u in got] == [b"\x01"]  # no sync seen yet


async def test_after_a_sync_data_is_held_until_the_next_sync_releases_all_universes(
    registry: ResourceRegistry,
) -> None:
    lease = await SacnReceiver.acquire(registry, "127.0.0.1", 0)
    receiver = lease.value
    got: list[UniverseUpdate] = []
    receiver.subscribe(1, got.append)
    receiver.subscribe(2, got.append)
    receiver._on_frame(protocol.decode_sync(protocol.encode_sync(OTHER_CID, 500, 0)), 0.0)
    receiver._on_frame(protocol.decode(synced(1, 0, b"\x01")), 0.01)
    receiver._on_frame(protocol.decode(synced(2, 0, b"\x02")), 0.01)
    receiver._on_frame(protocol.decode(synced(1, 1, b"\x03")), 0.02)  # newer data for 1
    assert got == []
    receiver._on_frame(protocol.decode_sync(protocol.encode_sync(OTHER_CID, 500, 1)), 0.03)
    assert sorted((u.universe, u.slots, u.counter.value) for u in got) == [(1, b"\x03", 2), (2, b"\x02", 1)]


async def test_when_sync_packets_stop_data_flows_again_after_the_timeout(registry: ResourceRegistry) -> None:
    lease = await SacnReceiver.acquire(registry, "127.0.0.1", 0)
    receiver = lease.value
    got: list[UniverseUpdate] = []
    receiver.subscribe(1, got.append)
    receiver._on_frame(protocol.decode_sync(protocol.encode_sync(OTHER_CID, 500, 0)), 0.0)
    receiver._on_frame(protocol.decode(synced(1, 0, b"\x01")), 1.0)
    assert got == []
    receiver._on_frame(protocol.decode(synced(1, 1, b"\x02")), 2.6)  # 2.6 s since the last sync
    assert [u.slots for u in got] == [b"\x02"]


async def test_another_sources_sync_does_not_release_data(registry: ResourceRegistry) -> None:
    lease = await SacnReceiver.acquire(registry, "127.0.0.1", 0)
    receiver = lease.value
    got: list[UniverseUpdate] = []
    receiver.subscribe(1, got.append)
    receiver._on_frame(protocol.decode_sync(protocol.encode_sync(OTHER_CID, 500, 0)), 0.0)
    receiver._on_frame(protocol.decode(synced(1, 0, b"\x01")), 0.01)
    receiver._on_frame(protocol.decode_sync(protocol.encode_sync(bytes(16), 500, 0)), 0.02)
    assert got == []


async def test_the_receiver_joins_a_sync_universes_group_when_data_names_it(registry: ResourceRegistry) -> None:
    lease = await SacnReceiver.acquire(registry, "127.0.0.1", 0)
    receiver = lease.value
    calls: list[str] = []
    receiver._socket.join_multicast = lambda group: calls.append(f"join {group}")
    receiver._socket.leave_multicast = lambda group: calls.append(f"leave {group}")
    receiver.subscribe(1, lambda u: None)
    receiver._on_frame(protocol.decode(synced(1, 0, b"\x01")), 0.0)
    receiver._on_frame(protocol.decode(synced(1, 1, b"\x01")), 0.0)
    assert calls == ["join 239.255.0.1", "join 239.255.1.244"]
    await lease.release()
    assert sorted(calls[2:]) == ["leave 239.255.0.1", "leave 239.255.1.244"]
