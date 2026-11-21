"""Runtime: when ticks happen, what nodes are told, and what never runs."""

from __future__ import annotations

import time

import anyio
import numpy as np
import pytest

from rasl.graph import CycleWarning, GraphBuilder
from rasl.graph.node import BaseNode, TickContext, pull_rate
from rasl.graph.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.runtime import DueTimes, Runtime, find_rate_drivers, find_undriven
from rasl.signal import Frame, MatrixPayload


class Probe(BaseNode):
    """A node that records every tick it is pulled at. Ports are its own."""

    def __init__(self, node_id: str, *, work: float = 0.0) -> None:
        self.id = node_id
        self.inputs = PortGroup.inputs(**{"in": InputPortSpec(MatrixPayload)})
        self.outputs = PortGroup.outputs(out=OutputPortSpec(MatrixPayload))
        self.ticks: list[TickContext] = []
        self.seen: list[float | None] = []
        self.work = work

    async def pull(self, tick: TickContext) -> None:
        self.ticks.append(tick)
        frame = self.inputs.get("in").read()
        self.seen.append(None if frame is None else float(np.asarray(frame.payload)[0, 0]))
        if self.work:
            time.sleep(self.work)  # a pull that hogs the event loop
        self.outputs.out.write(_frame(float(len(self.ticks))))


class Sink(Probe):
    """A Probe that drives the runtime at ``hz``."""

    def __init__(self, node_id: str, hz: float, *, work: float = 0.0) -> None:
        super().__init__(node_id, work=work)
        self.hz = hz

    @pull_rate(lambda self: self.hz)
    async def pull(self, tick: TickContext) -> None:
        await super().pull(tick)


class Pusher(Probe):
    """A push source: writes a rising value from a background task."""

    def __init__(self, node_id: str, interval: float) -> None:
        super().__init__(node_id)
        self.interval = interval
        self.writes = 0

    async def start(self, ctx) -> None:
        ctx.start_background(self._run)

    async def _run(self) -> None:
        while True:
            self.writes += 1
            self.outputs.out.write(_frame(float(self.writes)))
            await anyio.sleep(self.interval)

    async def pull(self, tick: TickContext) -> None:
        self.ticks.append(tick)


def _frame(value: float) -> Frame:
    return Frame(
        topic="test",
        timestamp=0.0,
        payload=MatrixPayload(np.full((1, 1), value, dtype=np.float32)),
    )


def _plan(nodes, edges=()):
    builder = GraphBuilder()
    for node in nodes:
        builder.add_node(node)
    for source, target in edges:
        builder.connect(source, "out", target, "in")
    return builder.build()


async def _run(runtime: Runtime, seconds: float) -> None:
    with anyio.move_on_after(seconds):
        await runtime.run()


class TestDueTimes:
    def test_every_driver_is_first_due_at_t0(self) -> None:
        due = DueTimes({"a": 30.0, "b": 20.0}, t0=100.0)
        assert due.next() == (100.0, ("a", "b"))

    def test_drivers_share_the_ticks_where_their_periods_meet(self) -> None:
        due = DueTimes({"a": 30.0, "b": 20.0}, t0=0.0)
        ticks = []
        for _ in range(9):
            at, drivers = due.next()
            ticks.append((round(at * 1000), drivers))
            due.advance(drivers, at)
        assert ticks == [
            (0, ("a", "b")),
            (33, ("a",)),
            (50, ("b",)),
            (67, ("a",)),
            (100, ("a", "b")),
            (133, ("a",)),
            (150, ("b",)),
            (167, ("a",)),
            (200, ("a", "b")),
        ]

    @pytest.mark.parametrize("hz", [0.5, 2.5, 7.0, 29.97])
    def test_any_positive_rate_keeps_its_own_period(self, hz: float) -> None:
        due = DueTimes({"a": hz}, t0=5.0)
        times = []
        for _ in range(40):
            at, drivers = due.next()
            times.append(at)
            due.advance(drivers, at)
        assert np.allclose(np.diff(times), 1.0 / hz, atol=1e-9)

    def test_less_than_a_period_late_runs_late(self) -> None:
        due = DueTimes({"a": 10.0}, t0=0.0)
        assert due.advance(["a"], now=0.19) == {}
        assert due.next()[0] == pytest.approx(0.1)

    def test_more_than_a_period_late_jumps_to_the_next_due_time(self) -> None:
        due = DueTimes({"a": 10.0}, t0=0.0)
        # ran the tick at 0, which took until 0.55: 0.1 to 0.5 are gone
        assert due.advance(["a"], now=0.55) == {"a": 5}
        assert due.next()[0] == pytest.approx(0.6)

    def test_a_slow_driver_does_not_make_a_fast_one_replay(self) -> None:
        due = DueTimes({"fast": 100.0, "slow": 1.0}, t0=0.0)
        dropped = due.advance(["fast", "slow"], now=0.255)
        assert dropped == {"fast": 25}
        assert due.next() == (pytest.approx(0.26), ("fast",))

    def test_resuming_keeps_each_driver_on_its_own_times(self) -> None:
        due = DueTimes({"a": 10.0, "b": 4.0}, t0=0.0, now=0.42)
        assert due.due("a") == pytest.approx(0.5)
        assert due.due("b") == pytest.approx(0.5)
        assert due.next() == (pytest.approx(0.5), ("a", "b"))


class TestWhatIsDriven:
    def test_rate_drivers_are_the_nodes_that_declare_a_rate(self) -> None:
        plan = _plan([Probe("src"), Sink("out", 25)], [("src", "out")])
        assert find_rate_drivers(plan) == {"out": 25.0}

    @pytest.mark.parametrize("hz", [0.0, -1.0, float("inf"), float("nan")])
    def test_a_rate_must_be_positive_and_finite(self, hz: float) -> None:
        with pytest.raises(ValueError, match="pull rate"):
            find_rate_drivers(_plan([Sink("out", hz)]))

    def test_nodes_not_upstream_of_a_rate_driver_are_undriven(self) -> None:
        plan = _plan(
            [Probe("src"), Probe("mid"), Sink("out", 10), Probe("stray"), Probe("dead_end")],
            [("src", "mid"), ("mid", "out"), ("src", "dead_end")],
        )
        assert sorted(find_undriven(plan)) == ["dead_end", "stray"]

    def test_with_no_rate_driver_every_node_is_undriven(self) -> None:
        plan = _plan([Probe("src"), Probe("out")], [("src", "out")])
        assert find_undriven(plan) == ["src", "out"]

    async def test_a_graph_nothing_drives_loads_and_idles(self) -> None:
        src, out = Probe("src"), Probe("out")
        runtime = Runtime(_plan([src, out], [("src", "out")]))
        await _run(runtime, 0.15)
        assert src.ticks == [] and out.ticks == []
        assert runtime.scheduler.tick_count == 0


class TestTicks:
    async def test_t_and_dt_are_the_due_times_not_the_wake_up_times(self) -> None:
        sink = Sink("out", 50)
        await _run(Runtime(_plan([sink])), 0.25)
        assert len(sink.ticks) >= 8
        assert [tick.tick for tick in sink.ticks] == list(range(len(sink.ticks)))
        assert np.allclose([tick.t for tick in sink.ticks], np.arange(len(sink.ticks)) / 50, atol=1e-9)
        # A sink is told its own dt, like any node (it used to be told 0)
        assert sink.ticks[0].dt == 0.0
        assert np.allclose([tick.dt for tick in sink.ticks[1:]], 1 / 50, atol=1e-9)

    async def test_the_scheduler_records_when_it_ran_and_last_ticked(self) -> None:
        runtime = Runtime(_plan([Sink("out", 50)]))
        assert runtime.scheduler.run_started_at == 0.0 and runtime.scheduler.last_tick_at is None
        before = time.monotonic()
        await _run(runtime, 0.2)
        scheduler = runtime.scheduler
        assert before <= scheduler.run_started_at <= time.monotonic()
        assert scheduler.last_tick_at is not None
        assert scheduler.run_started_at <= scheduler.last_tick_at <= time.monotonic()

    async def test_a_rate_below_one_hz_is_not_pulled_every_second(self) -> None:
        slow, fast = Sink("slow", 2.5), Sink("fast", 20)
        await _run(Runtime(_plan([slow, fast])), 0.9)
        assert [round(tick.t, 6) for tick in slow.ticks] == [0.0, 0.4, 0.8]

    async def test_a_shared_upstream_node_runs_once_per_tick_with_its_own_dt(self) -> None:
        src, a, b = Probe("src"), Sink("a", 30), Sink("b", 20)
        await _run(Runtime(_plan([src, a, b], [("src", "a"), ("src", "b")])), 0.3)
        expected = sorted({round(tick.t, 6) for tick in a.ticks + b.ticks})
        assert [round(tick.t, 6) for tick in src.ticks] == expected
        # 0, 1/30, 1/20, 2/30, 1/10: the step is uneven, and dt says so
        assert np.allclose([tick.dt for tick in src.ticks[1:5]], [1 / 30, 1 / 60, 1 / 60, 1 / 30], atol=1e-9)
        assert np.allclose(np.cumsum([tick.dt for tick in src.ticks]), [tick.t for tick in src.ticks], atol=1e-9)


class TestPush:
    async def test_a_pushed_frame_is_read_at_the_next_tick(self) -> None:
        src, out = Pusher("src", 0.01), Sink("out", 20)
        await _run(Runtime(_plan([src, out], [("src", "out")])), 0.3)
        seen = [value for value in out.seen if value is not None]
        assert len(seen) >= 4
        assert seen == sorted(seen) and seen[-1] > seen[0]  # the latest write each time

    async def test_a_push_never_causes_a_tick_or_wakes_the_scheduler(self) -> None:
        src, out = Pusher("src", 0.002), Sink("out", 10)
        runtime = Runtime(_plan([src, out], [("src", "out")]))
        sleeps = 0
        sleep_until = runtime.scheduler._sleep_until

        async def counted(target_time: float, should_stop) -> bool:
            nonlocal sleeps
            sleeps += 1
            return await sleep_until(target_time, should_stop)

        runtime.scheduler._sleep_until = counted
        await _run(runtime, 0.45)
        assert src.writes > 50
        assert len(out.ticks) == 5  # 0, 0.1, 0.2, 0.3, 0.4
        assert sleeps <= 6  # one sleep per tick, however many frames were pushed


class TestOverload:
    async def test_a_sink_that_cannot_keep_up_drops_ticks_and_the_loop_stays_live(self) -> None:
        sink = Sink("out", 100, work=0.03)  # 30 ms of work every 10 ms
        runtime = Runtime(_plan([sink]))
        others = 0

        async def other_work() -> None:
            nonlocal others
            while True:
                others += 1
                await anyio.sleep(0.01)

        started = time.monotonic()
        async with anyio.create_task_group() as tg:
            tg.start_soon(other_work)
            await _run(runtime, 0.5)  # used never to return: no await ever yielded
            tg.cancel_scope.cancel()
        assert time.monotonic() - started < 1.0

        assert others >= 5
        assert runtime.timing.dropped_ticks["out"] >= 10
        # It runs as often as it can, in step with the clock: no backlog builds up
        assert 10 <= len(sink.ticks) <= 20
        assert sink.ticks[-1].t == pytest.approx(time.monotonic() - started, abs=0.2)
        # dt carries the real gap, so time-based nodes stay right
        assert np.allclose(np.cumsum([tick.dt for tick in sink.ticks]), [tick.t for tick in sink.ticks], atol=1e-9)


class Faulty(Probe):
    """A node whose pull raises while ``broken`` is set."""

    def __init__(self, node_id: str) -> None:
        super().__init__(node_id)
        self.broken = True

    async def pull(self, tick: TickContext) -> None:
        if self.broken:
            self.ticks.append(tick)
            raise RuntimeError("boom")
        await super().pull(tick)


class TestFailures:
    @pytest.fixture(autouse=True)
    def quiet_logs(self):
        """Rendering a traceback takes longer than these tests' ticks."""
        import logging

        import structlog

        before = structlog.get_config()
        structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))
        yield
        structlog.configure(**before)

    async def test_a_failure_is_recorded_against_the_node_that_raised(self) -> None:
        src, bad, out, other = Probe("src"), Faulty("bad"), Sink("out", 50), Sink("other", 50)
        runtime = Runtime(_plan([src, bad, out, other], [("src", "bad"), ("bad", "out")]))
        await _run(runtime, 0.15)

        stats = runtime.monitor.to_dict()
        assert stats["bad"]["failure_count"] >= 3 and stats["bad"]["success_count"] == 0
        assert stats["bad"]["last_error"] == "boom"
        # Upstream of the failure ran; the sink it feeds was not reached
        assert stats["src"]["failure_count"] == 0 and stats["src"]["success_count"] >= 3
        assert "out" not in stats and out.ticks == []
        # A sink that does not depend on it is untouched
        assert stats["other"]["success_count"] >= 3 and stats["other"]["failure_count"] == 0

    async def test_by_default_a_failing_node_is_never_disabled(self) -> None:
        bad, out = Faulty("bad"), Sink("out", 100)
        runtime = Runtime(_plan([bad, out], [("bad", "out")]))
        await _run(runtime, 0.2)
        assert len(bad.ticks) >= 10 and out.ticks == []
        assert runtime.executor.disabled == set()

    async def test_a_node_that_keeps_failing_is_disabled_and_the_rest_goes_on(self) -> None:
        bad, out = Faulty("bad"), Sink("out", 100)
        runtime = Runtime(_plan([bad, out], [("bad", "out")]), max_consecutive_errors=3)
        await _run(runtime, 0.2)
        assert len(bad.ticks) == 3  # pulled three times, then left alone
        assert runtime.executor.disabled == {"bad"}
        assert len(out.ticks) >= 10  # the sink runs again once the node is out of the way
        assert all(value is None for value in out.seen)  # it never wrote a frame

    async def test_a_nodes_own_limit_overrides_the_runtimes(self) -> None:
        bad, out = Faulty("bad"), Sink("out", 100)
        bad.max_consecutive_errors = 2
        runtime = Runtime(_plan([bad, out], [("bad", "out")]), max_consecutive_errors=5)
        await _run(runtime, 0.2)
        assert len(bad.ticks) == 2 and runtime.executor.disabled == {"bad"}

    async def test_a_nodes_own_limit_of_zero_never_disables_it(self) -> None:
        bad, out = Faulty("bad"), Sink("out", 100)
        bad.max_consecutive_errors = 0
        runtime = Runtime(_plan([bad, out], [("bad", "out")]), max_consecutive_errors=3)
        await _run(runtime, 0.2)
        assert len(bad.ticks) >= 10 and runtime.executor.disabled == set()

    async def test_a_success_resets_the_count(self) -> None:
        bad, out = Faulty("bad"), Sink("out", 100)
        runtime = Runtime(_plan([bad, out], [("bad", "out")]), max_consecutive_errors=3)

        async def heal() -> None:
            while len(bad.ticks) < 2:
                await anyio.sleep(0.001)
            bad.broken = False

        async with anyio.create_task_group() as tg:
            tg.start_soon(heal)
            await _run(runtime, 0.2)
        assert runtime.executor.disabled == set()
        assert runtime.monitor.get_stats("bad").consecutive_failures == 0
        assert len(out.ticks) >= 5


class TestNodesOwnTheirPorts:
    """Nodes of one class do not share port objects (rasl-e7j)."""

    @pytest.fixture(autouse=True)
    def nodes(self):
        import rasl.nodes  # noqa: F401
        from rasl.graph.node import ensure_nodes_loaded

        ensure_nodes_loaded()

    def test_each_node_gets_its_own_ports_from_the_class_declaration(self) -> None:
        from rasl.nodes.effects.waveform import WaveformNode

        a = WaveformNode(WaveformNode.Config(id="a", output_channels=2))
        b = WaveformNode(WaveformNode.Config(id="b", output_channels=2))
        assert a.outputs.out is not b.outputs.out
        assert a.inputs.phase is not b.inputs.phase
        assert a.outputs.out is not WaveformNode.outputs.out
        assert a.outputs.out.spec is WaveformNode.outputs.out.spec

    async def test_three_sources_of_one_class_keep_their_own_values(self) -> None:
        from rasl.config.build import parse_config

        plan = parse_config(
            """
            graph {
                node Waveform low { shape square; duty 0; output_channels 2; }
                node Waveform high { shape square; duty 1; output_channels 2; }
                node Waveform ramp { shape sawtooth; frequency_hz 1; output_channels 2; }
                node ConsoleSink s1 { fps 50; connect low; }
                node ConsoleSink s2 { fps 50; connect high; }
                node ConsoleSink s3 { fps 50; connect ramp; }
            }
            """
        )
        runtime = Runtime(plan)
        await _run(runtime, 0.2)
        latest = {node: np.asarray(frame.payload).copy() for (node, _), frame in runtime.executor.latest.items()}
        np.testing.assert_allclose(latest["low"], 0.0)
        np.testing.assert_allclose(latest["high"], 1.0)
        assert 0.0 < float(latest["ramp"][0, 0]) < 1.0
        assert not np.shares_memory(latest["low"], latest["high"])

    async def test_an_unconnected_input_does_not_read_a_sibling_nodes_frame(self) -> None:
        a, b, out_a, out_b = Probe("a"), Probe("b"), Sink("out_a", 50), Sink("out_b", 50)
        src = Pusher("src", 0.005)
        runtime = Runtime(_plan([src, a, b, out_a, out_b], [("src", "a"), ("a", "out_a"), ("b", "out_b")]))
        await _run(runtime, 0.15)
        assert any(value is not None for value in a.seen)
        assert all(value is None for value in b.seen)
        assert not b.inputs.get("in").connected and a.inputs.get("in").connected


class TestMonitorOnUpdates:
    def test_forget_drops_and_end_streak_keeps_the_counts(self) -> None:
        from rasl.runtime.monitor import NodeMonitor

        monitor = NodeMonitor()
        for node_id in ("a", "b"):
            monitor.record_success(node_id, 1.0)
            monitor.record_failure(node_id, RuntimeError("x"), 1.0)
            monitor.record_failure(node_id, RuntimeError("x"), 1.0)
        monitor.forget({"a"})
        monitor.end_streak({"b"})
        assert monitor.get_stats("a") is None
        b = monitor.get_stats("b")
        assert b is not None and b.consecutive_failures == 0 and b.failure_count == 2


class TestNonMatrixPayloads:
    async def test_a_counter_reaches_its_reader_through_a_passthrough_untouched(self) -> None:
        from rasl.signal import RollingCounter

        class Counter(BaseNode):
            def __init__(self) -> None:
                self.id = "count"
                self.inputs = PortGroup.inputs()
                self.outputs = PortGroup.outputs(out=OutputPortSpec(RollingCounter))
                self.written: list[RollingCounter] = []

            async def pull(self, tick: TickContext) -> None:
                counter = RollingCounter(len(self.written))
                self.written.append(counter)
                self.outputs.out.write(Frame(topic="count", timestamp=0.0, payload=counter))

        class Reader(BaseNode):
            def __init__(self) -> None:
                self.id = "reader"
                self.inputs = PortGroup.inputs(**{"in": InputPortSpec(RollingCounter)})
                self.outputs = PortGroup.outputs()
                self.read: list[object] = []

            @pull_rate(lambda self: 50.0)
            async def pull(self, tick: TickContext) -> None:
                frame = self.inputs.get("in").read()
                self.read.append(None if frame is None else frame.payload)

        counter, reader = Counter(), Reader()
        await _run(Runtime(_plan([counter, reader], [("count", "reader")])), 0.15)
        assert reader.read and len(reader.read) == len(counter.written)
        assert all(got is sent for got, sent in zip(reader.read, counter.written))


class TestEndOfTick:
    """A shared resource with end_tick acts once per tick, after that tick's pulls."""

    async def test_end_tick_runs_after_every_due_pull_of_each_tick(self) -> None:
        from rasl.graph.node import ResourceKey

        log: list[str] = []

        class Recorder:
            def end_tick(self, tick: TickContext) -> None:
                log.append(f"end {round(tick.t, 6)}")

        class Holder(Sink):
            async def start(self, ctx) -> None:
                async def _open():
                    return Recorder()

                async def _close(value):
                    return None

                self._lease = await ctx.resources.acquire(ResourceKey("test.recorder"), _open, _close)

            @pull_rate(lambda self: self.hz)
            async def pull(self, tick: TickContext) -> None:
                log.append(f"pull {self.id} {round(tick.t, 6)}")

        a, b = Holder("a", 20), Holder("b", 20)
        await _run(Runtime(_plan([a, b])), 0.12)
        assert log[:6] == ["pull a 0.0", "pull b 0.0", "end 0.0", "pull a 0.05", "pull b 0.05", "end 0.05"]


class TestPushedOutputs:
    """An input fed by a pushed output reads it as last written; its writer is not pulled."""

    async def test_a_reader_of_a_pushed_output_does_not_pull_its_writer(self) -> None:
        class Writer(Probe):
            """Pushes on 'live' outside pull; is a rate driver of its own at 5 Hz."""

            def __init__(self, node_id: str) -> None:
                super().__init__(node_id)
                self.outputs = PortGroup.outputs(
                    out=OutputPortSpec(MatrixPayload), live=OutputPortSpec(MatrixPayload, pushed=True)
                )

            @pull_rate(5)
            async def pull(self, tick: TickContext) -> None:
                self.ticks.append(tick)

        src, writer, reader = Probe("src"), Writer("w"), Sink("r", 50)
        builder = GraphBuilder()
        for n in (src, writer, reader):
            builder.add_node(n)
        builder.connect("src", "out", "w", "in")
        builder.connect("w", "live", "r", "in")
        plan = builder.build()
        runtime = Runtime(plan)
        assert runtime._undriven == []  # w delivers by push; src feeds w, a driver
        await _run(runtime, 0.5)
        # w runs at its own 5 Hz (0, 0.2, 0.4), not at the reader's 50 Hz
        assert [round(t.t, 6) for t in writer.ticks] == [0.0, 0.2, 0.4]
        assert len(reader.ticks) >= 20


class TestRoutedInputs:
    """Inputs built from slices, through a running runtime (rasl-pd0.15)."""

    async def test_sliced_color_edges_from_three_nodes_of_one_class_assemble_in_order(self) -> None:
        from rasl.color import RgbColorPayload
        from rasl.graph import Slice

        class Fill(BaseNode):
            def __init__(self, node_id: str, value: float) -> None:
                self.id = node_id
                self.value = value
                self.inputs = PortGroup.inputs()
                self.outputs = PortGroup.outputs(out=OutputPortSpec(RgbColorPayload))

            async def pull(self, tick: TickContext) -> None:
                data = np.full((2, 3), self.value, dtype=np.float32)
                self.outputs.out.write(Frame(topic=self.id, timestamp=0.0, payload=RgbColorPayload(data)))

        class Strip(BaseNode):
            def __init__(self) -> None:
                self.id = "strip"
                self.inputs = PortGroup.inputs(**{"in": InputPortSpec(RgbColorPayload, count=6)})
                self.outputs = PortGroup.outputs()
                self.frames: list[Frame | None] = []

            @pull_rate(lambda self: 50.0)
            async def pull(self, tick: TickContext) -> None:
                frame = self.inputs.get("in").read()
                self.frames.append(frame)

        strip = Strip()
        builder = GraphBuilder()
        for node in (Fill("f0", 0.25), Fill("f1", 0.5), Fill("f2", 0.75), strip):
            builder.add_node(node)
        for i in range(3):
            builder.connect(f"f{i}", "out", "strip", "in", None, Slice(2 * i, 2 * i + 2))
        await _run(Runtime(builder.build()), 0.1)

        assert strip.frames and all(frame is not None for frame in strip.frames)
        last = strip.frames[-1]
        assert type(last.payload) is RgbColorPayload
        np.testing.assert_allclose(np.asarray(last.payload)[:, 0], [0.25, 0.25, 0.5, 0.5, 0.75, 0.75])

    async def test_a_sliced_back_edge_reads_the_previous_ticks_frame(self) -> None:
        from rasl.graph import Slice

        a, b, out = Probe("a"), Probe("b"), Sink("out", 50)
        builder = GraphBuilder()
        for node in (a, b, out):
            builder.add_node(node)
        builder.connect("a", "out", "b", "in")
        builder.connect("b", "out", "out", "in")
        builder.connect("b", "out", "a", "in", Slice(0, 1), Slice(0, 1))
        with pytest.warns(CycleWarning):
            plan = builder.build()
        await _run(Runtime(plan), 0.12)
        # b writes 1, 2, 3... at ticks 0, 1, 2...; a reads b's write from the tick before
        assert len(a.seen) >= 4
        assert a.seen[0] is None
        assert a.seen[1:] == [float(n) for n in range(1, len(a.seen))]


class _Ticker:
    """Runs a runtime's ticks one at a time, under the test's control (no scheduler)."""

    def __init__(self, runtime: Runtime, tg) -> None:
        self.runtime = runtime
        self.tg = tg
        self.n = 0

    async def tick(self) -> None:
        now = time.monotonic()
        await self.runtime._tick(TickContext(tick=self.n, t=self.n / 50, dt=0.02, wall_time=now), tuple(self.runtime._rate_drivers))
        self.n += 1


class _ticking:
    """``async with _ticking(runtime) as ticker``: nodes bound and started, stopped on exit."""

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    async def __aenter__(self) -> _Ticker:
        self._tg = anyio.create_task_group()
        tg = await self._tg.__aenter__()
        runtime = self.runtime
        runtime._host.attach(tg)
        runtime._host.bind_ports(runtime.plan)
        for node_id in runtime.plan.topological_order:
            await runtime._host.start(runtime.plan, node_id)
        return _Ticker(runtime, tg)

    async def __aexit__(self, *exc) -> None:
        await self.runtime._host.stop_all(self.runtime.plan)
        self._tg.cancel_scope.cancel()
        await self._tg.__aexit__(*exc)


def _matrix(value: float, rows: int = 2) -> np.ndarray:
    return np.full((rows, 1), value, dtype=np.float32)


class PushSource(BaseNode):
    """A push source with no pull; the test writes to it as a background task would."""

    def __init__(self, node_id: str = "src") -> None:
        self.id = node_id
        self.inputs = PortGroup.inputs()
        self.outputs = PortGroup.outputs(out=OutputPortSpec(MatrixPayload))

    def push(self, value: float) -> np.ndarray:
        buf = self.outputs.out.acquire(2)
        buf[:] = value
        self.outputs.out.commit(Frame(topic=self.id, timestamp=0.0, payload=MatrixPayload(buf)))
        return buf


class Reader(BaseNode):
    """A 50 Hz sink that records what it reads; ``during`` runs inside its pull, after the
    read, as work that awaits while background tasks run would."""

    def __init__(self, node_id: str = "reader") -> None:
        self.id = node_id
        self.inputs = PortGroup.inputs(**{"in": InputPortSpec(MatrixPayload)})
        self.outputs = PortGroup.outputs()
        self.during = None
        self.read: list[list[float] | None] = []

    @pull_rate(lambda self: 50.0)
    async def pull(self, tick: TickContext) -> None:
        frame = self.inputs.get("in").read()
        if self.during is not None:
            self.during()
        self.read.append(None if frame is None else np.asarray(frame.payload).ravel().tolist())


class TestPortPublishing:
    """When frames become visible, and how long they stay unchanged (rasl-pd0.12)."""

    async def test_pushes_during_a_pull_do_not_change_the_frame_it_read(self) -> None:
        src, reader = PushSource(), Reader()
        async with _ticking(Runtime(_plan([src, reader], [("src", "reader")]))) as ticker:
            src.push(1.0)
            await ticker.tick()
            seen_in_tick: list[list[float]] = []

            def pushes_mid_pull() -> None:
                src.push(2.0)
                src.push(3.0)
                frame = reader.inputs.get("in").read()
                seen_in_tick.append(np.asarray(frame.payload).ravel().tolist())

            reader.during = pushes_mid_pull
            await ticker.tick()
            reader.during = None
            await ticker.tick()
        assert reader.read == [[1.0, 1.0], [1.0, 1.0], [3.0, 3.0]]
        assert seen_in_tick == [[1.0, 1.0]]

    async def test_a_push_becomes_visible_at_the_next_tick_not_mid_tick(self) -> None:
        src, early, late = PushSource(), Reader("early"), Reader("late")
        runtime = Runtime(_plan([src, early, late], [("src", "early"), ("src", "late")]))
        async with _ticking(runtime) as ticker:
            src.push(1.0)
            await ticker.tick()
            early.during = lambda: src.push(5.0)
            await ticker.tick()
            early.during = None
            await ticker.tick()
        # Every reader in a tick sees the same pushed frame
        assert early.read == late.read == [[1.0, 1.0], [1.0, 1.0], [5.0, 5.0]]

    async def test_an_unconnected_node_with_pull_publishes_in_its_own_tick(self) -> None:
        reader = Reader()

        class Counter(BaseNode):
            def __init__(self) -> None:
                self.id = "count"
                self.inputs = PortGroup.inputs()
                self.outputs = PortGroup.outputs(out=OutputPortSpec(MatrixPayload))
                self.n = 0

            async def pull(self, tick: TickContext) -> None:
                self.n += 1
                buf = self.outputs.out.acquire(2)
                buf[:] = self.n
                self.outputs.out.commit(Frame(topic="c", timestamp=0.0, payload=MatrixPayload(buf)))

        async with _ticking(Runtime(_plan([Counter(), reader], [("count", "reader")]))) as ticker:
            for _ in range(3):
                await ticker.tick()
        assert reader.read == [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]

    async def test_what_a_failed_pull_wrote_is_never_published(self) -> None:
        reader = Reader()

        class Flaky(BaseNode):
            """Writes 1, then writes 2 and raises, then writes nothing."""

            def __init__(self) -> None:
                self.id = "flaky"
                self.inputs = PortGroup.inputs()
                self.outputs = PortGroup.outputs(out=OutputPortSpec(MatrixPayload))
                self.n = 0

            async def pull(self, tick: TickContext) -> None:
                self.n += 1
                if self.n <= 2:
                    self.outputs.out.write(Frame(topic="f", timestamp=0.0, payload=MatrixPayload(_matrix(self.n))))
                if self.n == 2:
                    raise RuntimeError("fails after writing")

        runtime = Runtime(_plan([Flaky(), reader], [("flaky", "reader")]))
        async with _ticking(runtime) as ticker:
            for _ in range(3):
                await ticker.tick()
        # Tick 1's pull failed, so the reader was not pulled; tick 2 reads the last good frame
        assert reader.read == [[1.0, 1.0], [1.0, 1.0]]

    async def test_forget_publishes_nothing_and_the_next_tick_does(self) -> None:
        src, reader = PushSource(), Reader()
        runtime = Runtime(_plan([src, reader], [("src", "reader")]))
        async with _ticking(runtime) as ticker:
            src.push(1.0)
            await ticker.tick()
            src.push(2.0)
            runtime.executor.forget(set())
            assert np.asarray(runtime.executor.latest[("src", "out")].payload).ravel().tolist() == [1.0, 1.0]
            await ticker.tick()
        assert reader.read[-1] == [2.0, 2.0]

    async def test_a_plan_update_keeps_a_kept_nodes_buffers(self) -> None:
        src, reader = PushSource(), Reader()
        runtime = Runtime(_plan([src, reader], [("src", "reader")]))
        async with _ticking(runtime) as ticker:
            first = src.push(1.0)
            await ticker.tick()
            runtime._host.bind_ports(runtime.plan)  # as a plan update does
            src.push(2.0)
            await ticker.tick()
            third = src.push(3.0)
        assert np.shares_memory(first, third)


class TestDebugFrames:
    """``Runtime(debug_frames=True)``: frame-lifetime mistakes fail the node (rasl-pd0.12)."""

    async def test_forwarding_a_port_owned_frame_without_detach_fails_the_forwarder(self) -> None:
        class Forward(BaseNode):
            def __init__(self, detach: bool) -> None:
                self.id = "fwd"
                self.detach = detach
                self.inputs = PortGroup.inputs(**{"in": InputPortSpec(MatrixPayload)})
                self.outputs = PortGroup.outputs(out=OutputPortSpec(MatrixPayload))

            async def pull(self, tick: TickContext) -> None:
                frame = self.inputs.get("in").read()
                if frame is not None:
                    self.outputs.out.write(frame.detach() if self.detach else frame)

        for detach, failures in ((False, 2), (True, 0)):
            src, reader = PushSource(), Reader()
            runtime = Runtime(_plan([src, Forward(detach), reader], [("src", "fwd"), ("fwd", "reader")]), debug_frames=True)
            async with _ticking(runtime) as ticker:
                src.push(1.0)
                await ticker.tick()
                await ticker.tick()
            stats = runtime.monitor.get_stats("fwd")
            assert (stats.failure_count if stats else 0) == failures

    async def test_reading_a_recycled_frame_fails(self) -> None:
        from rasl.graph.ports import FrameLifetimeError

        runtime = Runtime(_plan([PushSource(), Reader()], [("src", "reader")]), debug_frames=True)
        runtime.executor.latest[("src", "out")] = Frame(
            topic="t", timestamp=0.0, payload=MatrixPayload(np.full((2, 1), np.nan, dtype=np.float32))
        )
        with pytest.raises(FrameLifetimeError, match="src.out"):
            runtime.executor._resolve("src", "out", True, 0)
