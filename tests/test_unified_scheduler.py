"""UnifiedScheduler: when ticks happen, what nodes are told, and what never runs."""

from __future__ import annotations

import time

import anyio
import numpy as np
import pytest

from rasl.engine import GraphBuilder
from rasl.engine.frames import Frame, MatrixPayload
from rasl.engine.nodes import BaseNode
from rasl.engine.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.engine.tick import TickContext, pull_rate
from rasl.runtime import UnifiedScheduler
from rasl.runtime.unified import DueTimes, find_rate_drivers, find_undriven


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
    """A Probe that drives the scheduler at ``hz``."""

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


async def _run(scheduler: UnifiedScheduler, seconds: float) -> None:
    with anyio.move_on_after(seconds):
        await scheduler.run()


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
        scheduler = UnifiedScheduler(_plan([src, out], [("src", "out")]))
        await _run(scheduler, 0.15)
        assert src.ticks == [] and out.ticks == []
        assert scheduler._tick == 0


class TestTicks:
    async def test_t_and_dt_are_the_due_times_not_the_wake_up_times(self) -> None:
        sink = Sink("out", 50)
        await _run(UnifiedScheduler(_plan([sink])), 0.25)
        assert len(sink.ticks) >= 8
        assert [tick.tick for tick in sink.ticks] == list(range(len(sink.ticks)))
        assert np.allclose([tick.t for tick in sink.ticks], np.arange(len(sink.ticks)) / 50, atol=1e-9)
        # A sink is told its own dt, like any node (it used to be told 0)
        assert sink.ticks[0].dt == 0.0
        assert np.allclose([tick.dt for tick in sink.ticks[1:]], 1 / 50, atol=1e-9)

    async def test_a_rate_below_one_hz_is_not_pulled_every_second(self) -> None:
        slow, fast = Sink("slow", 2.5), Sink("fast", 20)
        await _run(UnifiedScheduler(_plan([slow, fast])), 0.9)
        assert [round(tick.t, 6) for tick in slow.ticks] == [0.0, 0.4, 0.8]

    async def test_a_shared_upstream_node_runs_once_per_tick_with_its_own_dt(self) -> None:
        src, a, b = Probe("src"), Sink("a", 30), Sink("b", 20)
        await _run(UnifiedScheduler(_plan([src, a, b], [("src", "a"), ("src", "b")])), 0.3)
        expected = sorted({round(tick.t, 6) for tick in a.ticks + b.ticks})
        assert [round(tick.t, 6) for tick in src.ticks] == expected
        # 0, 1/30, 1/20, 2/30, 1/10: the step is uneven, and dt says so
        assert np.allclose([tick.dt for tick in src.ticks[1:5]], [1 / 30, 1 / 60, 1 / 60, 1 / 30], atol=1e-9)
        assert np.allclose(np.cumsum([tick.dt for tick in src.ticks]), [tick.t for tick in src.ticks], atol=1e-9)


class TestPush:
    async def test_a_pushed_frame_is_read_at_the_next_tick(self) -> None:
        src, out = Pusher("src", 0.01), Sink("out", 20)
        await _run(UnifiedScheduler(_plan([src, out], [("src", "out")])), 0.3)
        seen = [value for value in out.seen if value is not None]
        assert len(seen) >= 4
        assert seen == sorted(seen) and seen[-1] > seen[0]  # the latest write each time

    async def test_a_push_never_causes_a_tick_or_wakes_the_scheduler(self) -> None:
        src, out = Pusher("src", 0.002), Sink("out", 10)
        scheduler = UnifiedScheduler(_plan([src, out], [("src", "out")]))
        sleeps = 0
        sleep_until = scheduler._sleep_until

        async def counted(target_time: float) -> bool:
            nonlocal sleeps
            sleeps += 1
            return await sleep_until(target_time)

        scheduler._sleep_until = counted
        await _run(scheduler, 0.45)
        assert src.writes > 50
        assert len(out.ticks) == 5  # 0, 0.1, 0.2, 0.3, 0.4
        assert sleeps <= 6  # one sleep per tick, however many frames were pushed


class TestOverload:
    async def test_a_sink_that_cannot_keep_up_drops_ticks_and_the_loop_stays_live(self) -> None:
        sink = Sink("out", 100, work=0.03)  # 30 ms of work every 10 ms
        scheduler = UnifiedScheduler(_plan([sink]))
        others = 0

        async def other_work() -> None:
            nonlocal others
            while True:
                others += 1
                await anyio.sleep(0.01)

        started = time.monotonic()
        async with anyio.create_task_group() as tg:
            tg.start_soon(other_work)
            await _run(scheduler, 0.5)  # used never to return: no await ever yielded
            tg.cancel_scope.cancel()
        assert time.monotonic() - started < 1.0

        assert others >= 5
        assert scheduler._timing.dropped_ticks["out"] >= 10
        # It runs as often as it can, in step with the clock: no backlog builds up
        assert 10 <= len(sink.ticks) <= 20
        assert sink.ticks[-1].t == pytest.approx(time.monotonic() - started, abs=0.2)
        # dt carries the real gap, so time-based nodes stay right
        assert np.allclose(np.cumsum([tick.dt for tick in sink.ticks]), [tick.t for tick in sink.ticks], atol=1e-9)
