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


def universe_node(settings: str = f"universe 1; channels 6; bind \"127.0.0.1\"; port {PORT};"):
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


def test_its_ports_are_dmx_in_and_dmx_count_and_terminated_out() -> None:
    node = universe_node()
    assert list(node.outputs.names) == ["dmx", "count", "terminated"]
    assert list(node.inputs.names) == ["dmx"]


# ---- sending ---------------------------------------------------------------------------

from structlog.testing import capture_logs  # noqa: E402

from rasl.config.document import ConfigError  # noqa: E402
from rasl.runtime import pull_rate_of  # noqa: E402
from rasl.signal import Frame, MatrixPayload  # noqa: E402


class FakeSocket:
    """Records what a sender sends."""

    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def sendto(self, packet: bytes, address: tuple[str, int]) -> None:
        self.sent.append((packet, address))

    def setsockopt(self, *args) -> None:
        pass

    def close(self) -> None:
        pass


async def started_sender(registry: ResourceRegistry, settings: str = "universe 3; channels 4;") -> tuple[Any, Context, FakeSocket]:
    node = universe_node(settings)
    c = Context(registry, Wiring(inputs=frozenset({"dmx"})))
    await node.start(c.ctx)
    sender = node._output.value._sender.value
    real, sender._socket = sender._socket, FakeSocket()
    real.close()
    return node, c, sender._socket


def feed(node, values) -> None:
    """Put a frame on the node's dmx input, as routing would."""
    node.inputs.dmx._frame = Frame(topic="t", timestamp=0.0, payload=MatrixPayload(np.asarray(values, dtype=np.float32)))


async def test_a_wired_input_opens_only_the_output_and_sends_encoded_slots(registry: ResourceRegistry) -> None:
    node, c, sock = await started_sender(registry)
    assert node._receiver is None
    await node.pull(None)
    assert sock.sent == []  # nothing before the first frame
    feed(node, [[1.0, 0.5], [-1.0, 2.0], [0.2, 0.0], [0.9, 0.9]])  # 8 values for 4 channels
    await node.pull(None)
    packet, address = sock.sent[0]
    frame = protocol.decode(packet)
    assert address == ("239.255.0.3", 5568)
    assert list(frame.slots) == [255, 127, 0, 255]  # row-major, clipped, truncated, cut
    feed(node, [[1.0]])
    await node.pull(None)
    assert list(protocol.decode(sock.sent[1][0]).slots) == [255, 0, 0, 0]  # padded
    await node.stop(c.ctx)
    assert [protocol.decode(p).terminated for p, _ in sock.sent[2:]] == [True, True, True]


async def test_both_directions_open_both(registry: ResourceRegistry) -> None:
    node = universe_node()
    c = Context(registry, Wiring(inputs=frozenset({"dmx"}), outputs=frozenset({"dmx"})))
    await node.start(c.ctx)
    assert node._output is not None and node._receiver is not None
    await node.stop(c.ctx)


def test_it_drives_the_graph_only_when_it_sends() -> None:
    node = universe_node("universe 1; fps 20hz;")
    assert pull_rate_of("u", node, Wiring(inputs=frozenset({"dmx"}))) == 20.0
    assert pull_rate_of("u", node, Wiring(outputs=frozenset({"dmx"}))) is None
    assert pull_rate_of("u", universe_node("universe 1;"), Wiring(inputs=frozenset({"dmx"}))) == 40.0


@pytest.mark.parametrize("fps", ["0.5hz", "1001hz"])
def test_fps_outside_1_to_1000_hz_is_refused(fps: str) -> None:
    with pytest.raises(ConfigError, match="between 1hz and 1000hz"):
        universe_node(f"universe 1; fps {fps};")


def test_dmx_is_the_input_as_a_target_and_the_output_as_a_source() -> None:
    plan = parse_config(
        "graph {\n"
        "    node SineSource s { output_channels 4; }\n"
        "    node SacnUniverse u { universe 1; connect s; }\n"
        "    node ConsoleSink c { fps 1; connect u; }\n"
        "}\n"
    )
    (into,) = plan.adjacency["s"]
    (out_of,) = plan.adjacency["u"]
    assert (into.target, into.target_port) == ("u", "dmx")
    assert (out_of.source_port, out_of.target) == ("dmx", "c")


def test_sending_universe_0_needs_a_target() -> None:
    with pytest.raises((ConfigError, ValueError), match="target"):
        parse_config("graph {\n    node SineSource s { output_channels 4; }\n    node SacnUniverse u { universe 0; connect s; }\n}\n")
    parse_config(
        "graph {\n    node SineSource s { output_channels 4; }\n"
        "    node SacnUniverse u { universe 0; target \"10.0.0.2\"; connect s; }\n}\n"
    )


def test_a_source_name_longer_than_63_bytes_is_refused() -> None:
    with pytest.raises(ConfigError, match="63 bytes"):
        universe_node(f"universe 1; source_name \"{'é' * 32}\";")


def _warnings(config: str) -> list[str]:
    with capture_logs() as logs:
        parse_config(config)
    return [entry["detail"] for entry in logs if entry["event"] == "config.warning"]


def test_two_nodes_sending_one_universe_load_with_a_warning() -> None:
    """Owner, Q20: a warning, not an error."""
    details = _warnings(
        "graph {\n    node SineSource s { output_channels 4; }\n"
        "    node SacnUniverse a { universe 5; connect s; }\n"
        "    node SacnUniverse b { universe 5; connect s; }\n"
        "    node SacnUniverse c { universe 5; target \"10.0.0.2\"; connect s; }\n}\n"
    )
    assert len(details) == 1
    assert "rasl/sacn-duplicate" in details[0] and "'b' and 'a' both send universe 5" in details[0]


@pytest.mark.parametrize(
    ("rates", "warned"),
    [((40, 40), False), ((40, 20), False), ((40, 10), False), ((40, 30), True)],
)
def test_sync_groups_warn_when_rates_rarely_share_a_tick(rates: tuple[int, int], warned: bool) -> None:
    a, b = rates
    details = _warnings(
        "graph {\n    node SineSource s { output_channels 4; }\n"
        f"    node SacnUniverse a {{ universe 1; sync 9; fps {a}hz; connect s; }}\n"
        f"    node SacnUniverse b {{ universe 2; sync 9; fps {b}hz; connect s; }}\n}}\n"
    )
    assert any("rasl/sacn-sync-rate" in d for d in details) is warned


async def test_end_to_end_two_synchronized_universes_send_data_then_one_sync_per_tick() -> None:
    """Over loopback: each tick sends universe 1, universe 2, then one sync packet."""
    from rasl.runtime import Runtime

    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        rx.bind(("127.0.0.1", 5568))
    except OSError:
        rx.close()
        pytest.skip("port 5568 is in use")
    rx.setblocking(False)
    plan = parse_config(
        "graph {\n    node SineSource s { output_channels 6; }\n"
        "    node SacnUniverse a { universe 1; target \"127.0.0.1\"; sync 9; fps 20hz; connect s; }\n"
        "    node SacnUniverse b { universe 2; target \"127.0.0.1\"; sync 9; fps 20hz; connect s; }\n"
        "}\n"
    )
    runtime = Runtime(plan)
    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(runtime.run)
            await anyio.sleep(0.13)
            tg.cancel_scope.cancel()
        packets = []
        while True:
            try:
                packets.append(rx.recv(2048))
            except BlockingIOError:
                break
    finally:
        rx.close()
    kinds = []
    for raw in packets:
        data, sync = protocol.decode(raw), protocol.decode_sync(raw)
        if sync is not None:
            kinds.append(f"sync {sync.sync_universe}")
        elif data.terminated:
            kinds.append(f"end {data.universe}")
        else:
            kinds.append(f"data {data.universe}")
    # Three ticks (0, 50, 100 ms), then three termination packets per universe at stop
    ticks = [k for k in kinds if not k.startswith("end")]
    assert ticks[:6] == ["data 1", "data 2", "sync 9"] * 2
    assert kinds.count("end 1") == 3 and kinds.count("end 2") == 3


async def test_a_node_wired_both_ways_sends_at_its_own_rate_whatever_reads_its_outputs() -> None:
    """Owner, 2026-11-21: received outputs are pushed, so a fast consumer does not pull the sender."""
    from rasl.runtime import Runtime

    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        rx.bind(("127.0.0.1", 5568))
    except OSError:
        rx.close()
        pytest.skip("port 5568 is in use")
    rx.setblocking(False)
    plan = parse_config(
        "graph {\n    node SineSource s { output_channels 3; }\n"
        f"    node SacnUniverse u {{ universe 4; target \"127.0.0.1\"; fps 5hz; bind \"127.0.0.1\"; port {PORT}; connect s; }}\n"
        "    node ConsoleSink c { fps 50; connect u; }\n"
        "}\n"
    )
    runtime = Runtime(plan)
    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(runtime.run)
            await anyio.sleep(0.5)
            tg.cancel_scope.cancel()
        data = []
        while True:
            try:
                frame = protocol.decode(rx.recv(2048))
            except BlockingIOError:
                break
            if frame is not None and not frame.terminated:
                data.append(frame)
    finally:
        rx.close()
    assert 2 <= len(data) <= 4  # about 5 a second, not 50


class TestRawChannelsIntoColor:
    """Color regroups plain values into its model's elements; a count that cannot divide is refused at load."""

    def test_a_count_that_divides_loads(self) -> None:
        parse_config("graph {\n    node SacnUniverse u { universe 1; channels 510; }\n    node Color c rgb { connect u; }\n}\n")

    def test_the_default_512_into_rgb_is_a_located_error_that_says_what_fits(self) -> None:
        with pytest.raises(ConfigError) as caught:
            parse_config("graph {\n    node SacnUniverse u { universe 1; }\n    node Color c rgb { connect u; }\n}\n")
        message = str(caught.value)
        assert "rasl/connect" in message and ":3:" in message
        assert "512 values by u.dmx (512 rows × 1)" in message
        assert "e.g. connect u.dmx[0~510]" in message

    def test_the_same_count_through_reshape_gets_the_same_hint(self) -> None:
        with pytest.raises(ConfigError, match=r"connect u\.dmx\[0~510\]"):
            parse_config("graph {\n    node SacnUniverse u { universe 1; }\n    node Reshape r { components 3; connect u; }\n}\n")


async def test_a_start_that_fails_partway_gives_back_what_it_acquired(registry: ResourceRegistry) -> None:
    """Review fix: the receive port is taken, so the half-acquired output is released."""
    blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    blocker.bind(("", 0))
    port = blocker.getsockname()[1]
    try:
        node = universe_node(f"universe 1; bind \"127.0.0.1\"; port {port};")
        c = Context(registry, Wiring(inputs=frozenset({"dmx"}), outputs=frozenset({"dmx"})))
        with pytest.raises(OSError):
            await node.start(c.ctx)
        assert node._output is None and node._receiver is None
        assert registry._entries == {}
    finally:
        blocker.close()


def test_two_senders_of_one_universe_warn_even_from_different_local_ports() -> None:
    details = _warnings(
        "graph {\n    node SineSource s { output_channels 4; }\n"
        "    node SacnUniverse a { universe 5; connect s; }\n"
        "    node SacnUniverse b { universe 5; send_port 46001; connect s; }\n}\n"
    )
    assert any("rasl/sacn-duplicate" in d for d in details)


@pytest.mark.parametrize(
    "broken",
    [
        lambda cls, plan, ids: [("nope", "rasl/x", "unknown node")],
        lambda cls, plan, ids: [(ids[0], "not a code", "bad code")],
        lambda cls, plan, ids: 1 / 0,
    ],
)
def test_a_broken_plan_warnings_hook_is_logged_and_the_config_still_loads(broken, monkeypatch) -> None:
    from rasl.devices.sacn.universe import SacnUniverseNode

    monkeypatch.setattr(SacnUniverseNode, "plan_warnings", classmethod(broken))
    with capture_logs() as logs:
        parse_config("graph {\n    node SacnUniverse u { universe 1; }\n}\n")
    assert any(entry["event"] == "plan_warnings_failed" for entry in logs)


class TestDirectionWarnings:
    """Owner, 2026-11-21: warn on settings and wiring that will not do what they look like."""

    def test_send_settings_on_a_node_that_only_receives(self) -> None:
        details = _warnings(
            "graph {\n    node SacnUniverse u { universe 1; target \"10.0.0.2\"; priority 150; }\n"
            "    node ConsoleSink c { fps 1; connect u; }\n}\n"
        )
        assert any("rasl/sacn-send-settings" in d and "priority, target" in d for d in details)

    def test_receiving_a_universe_this_rasl_sends(self) -> None:
        details = _warnings(
            "graph {\n    node SineSource s { output_channels 3; }\n"
            "    node SacnUniverse out { universe 7; connect s; }\n"
            "    node SacnUniverse back { universe 7; }\n"
            "    node ConsoleSink c { fps 1; connect back; }\n}\n"
        )
        assert any("rasl/sacn-own-universe" in d and "'out' sends" in d for d in details)

    def test_more_values_than_channels(self) -> None:
        details = _warnings(
            "graph {\n    node SacnUniverse src { universe 1; channels 30; }\n"
            "    node SacnUniverse out { universe 2; channels 20; connect src; }\n}\n"
        )
        assert any("rasl/sacn-truncated" in d and "fed 30 values but sends 20" in d for d in details)

    def test_a_plain_receiver_and_a_plain_sender_warn_nothing(self) -> None:
        assert _warnings(
            "graph {\n    node SacnUniverse a { universe 1; channels 6; }\n"
            "    node SacnUniverse b { universe 2; channels 6; connect a; }\n}\n"
        ) == []


def test_the_multiple_hint_suggests_rows_that_really_fit() -> None:
    """5 rows x 2 columns into Reshape 3: 3 rows (6 values) fit, not 4 (8 values)."""
    from rasl.graph import GraphBuilder, PortValuesError
    from rasl.graph.node import BaseNode, TickContext
    from rasl.graph.ports import OutputPortSpec, PortGroup
    from rasl.nodes.effects.reshape import ReshapeNode

    class Src(BaseNode):
        def __init__(self) -> None:
            self.id = "src"
            self.inputs = PortGroup.inputs()
            self.outputs = PortGroup.outputs(out=OutputPortSpec(MatrixPayload, count=5, components=2))

        async def pull(self, tick: TickContext) -> None:
            """Do nothing."""

    builder = GraphBuilder()
    builder.add_node(Src())
    builder.add_node(ReshapeNode(ReshapeNode.Config(id="r", components=3)))
    builder.connect("src", "out", "r", "input")
    with pytest.raises(PortValuesError, match=r"connect src\.out\[0~3\]"):
        builder.build()
