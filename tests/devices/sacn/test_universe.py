"""SacnUniverse: one universe; it receives when an output is wired, and writes facts only."""

from __future__ import annotations

import socket
from typing import Any

import anyio
import numpy as np
import pytest
import structlog

from rasl.config.build import parse_config
from rasl.devices.sacn import protocol
from rasl.graph.node import NodeContext, Wiring
from rasl.runtime.resources import ResourceRegistry
from rasl.signal import BoolPayload, RollingCounter

OTHER_CID = bytes(range(16))


def packet(sequence: int, slots: bytes, *, terminated: bool = False) -> bytes:
    """One E1.31 data packet for universe 1."""
    return protocol.encode_data(OTHER_CID, 1, sequence, 100, "src", slots, terminated=terminated)


def free_port() -> int:
    """A UDP port nothing is bound to right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = free_port()


def universe_node(settings: str = f"universe 1; channels 6; bind_address \"127.0.0.1\"; port {PORT};"):
    """A SacnUniverse built from config, with nothing connected."""
    plan = parse_config(f"graph {{\n    node SacnUniverse u {{ {settings} }}\n}}\n")
    return plan.nodes["u"]


class Context:
    """A NodeContext whose injected frames are recorded."""

    def __init__(self, registry: ResourceRegistry, wiring: Wiring) -> None:
        self.frames: list[tuple[str, Any]] = []
        self.ctx = NodeContext(
            node_id="u",
            logger=structlog.get_logger(),
            resources=registry,
            wiring=wiring,
            _start_background=lambda fn, args: None,
            _inject=lambda port, frame: self.frames.append((port, frame)),
        )

    def on(self, port: str) -> list[Any]:
        """Payloads injected on ``port``, in order."""
        return [frame.payload for name, frame in self.frames if name == port]


@pytest.fixture
async def registry():
    registry = ResourceRegistry()
    yield registry
    await registry.close_all()


async def until(condition, timeout: float = 2.0) -> None:
    """Wait for ``condition()`` to hold."""
    with anyio.fail_after(timeout):
        while not condition():
            await anyio.sleep(0.005)


async def test_with_nothing_wired_it_opens_nothing(registry: ResourceRegistry) -> None:
    node, c = universe_node(), Context(registry, Wiring())
    await node.start(c.ctx)
    assert registry._entries == {}
    await node.stop(c.ctx)


async def test_a_wired_output_opens_the_receiver_and_writes_raw_channels(registry: ResourceRegistry) -> None:
    node = universe_node()
    c = Context(registry, Wiring(outputs=frozenset({"dmx"})))
    await node.start(c.ctx)
    receiver = node._receiver.value
    receiver._listener.on_data(packet(0, bytes([255, 0, 51])), 0.0)  # 3 of 6 slots
    await until(lambda: c.on("dmx"))
    values = c.on("dmx")[0].data
    assert values.shape == (6, 1)
    np.testing.assert_allclose(values[:, 0], [1.0, 0.0, 0.2, 0.0, 0.0, 0.0])
    assert c.on("count") == [RollingCounter(1)]
    assert [p.data.ravel().tolist() for p in c.on("terminated")] == [[0.0]]
    frame = next(frame for name, frame in c.frames if name == "dmx")
    assert frame.topic == "sacn.universe.1"
    assert frame.metadata["sourceCid"] == OTHER_CID.hex()
    assert frame.metadata["sourceName"] == "src"
    await node.stop(c.ctx)
    assert registry._entries == {}  # its release closed the receiver


async def test_identical_packets_advance_count_and_terminated_flips_and_resumes(
    registry: ResourceRegistry,
) -> None:
    node = universe_node()
    c = Context(registry, Wiring(outputs=frozenset({"count", "terminated"})))
    await node.start(c.ctx)
    on_data = node._receiver.value._listener.on_data
    on_data(packet(0, b"\x01"), 0.0)
    on_data(packet(1, b"\x01"), 0.0)
    on_data(packet(2, b"\x01", terminated=True), 0.0)
    on_data(packet(10, b"\x02"), 0.0)  # the source comes back
    await until(lambda: len(c.on("count")) == 3)
    await anyio.sleep(0.02)
    assert [p.value for p in c.on("count")] == [1, 2, 3]
    flags = [bool(p.data.ravel()[0]) for p in c.on("terminated")]
    assert flags == [False, True, False]
    assert all(isinstance(p, BoolPayload) for p in c.on("terminated"))
    await node.stop(c.ctx)


async def test_a_stopped_node_writes_nothing(registry: ResourceRegistry) -> None:
    node = universe_node()
    c = Context(registry, Wiring(outputs=frozenset({"dmx"})))
    await node.start(c.ctx)
    listener = node._receiver.value._listener
    other = Context(registry, Wiring(outputs=frozenset({"dmx"})))
    keeper = universe_node()
    await keeper.start(other.ctx)  # keeps the shared receiver open
    await node.stop(c.ctx)
    listener.on_data(packet(0, b"\x01"), 0.0)
    await until(lambda: other.on("dmx"))
    assert c.on("dmx") == []
    await keeper.stop(other.ctx)


def test_its_ports_are_dmx_count_and_terminated() -> None:
    node = universe_node()
    assert list(node.outputs.names) == ["dmx", "count", "terminated"]
    assert list(node.inputs.names) == []
