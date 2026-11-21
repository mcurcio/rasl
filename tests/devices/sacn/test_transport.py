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
