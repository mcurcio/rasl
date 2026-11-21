"""Per-tick cost of routing frames between nodes, for before/after comparisons.

Runs a fixed set of graphs through the runtime's tick (no real-time scheduler, no sleeps)
and prints the median microseconds per tick of several runs. The graphs exercise the
paths the port buffers touch: fan-in of sliced edges, a repeat, a chain of passthrough
edges, a sliced back-edge, a large acquire/commit output, and a push source that commits
several times between ticks.

Usage:
    uv run python scripts/bench_ticks.py [--ticks 2000] [--runs 7]

Numbers are only comparable on one machine, run back to back.
"""

from __future__ import annotations

import argparse
import logging
import statistics
import time
import warnings
from typing import Callable

import anyio
import numpy as np
import structlog

from rasl.color import RgbColorPayload
from rasl.graph import CycleWarning, ExecutionPlan, GraphBuilder, Slice
from rasl.graph.node import BaseNode, TickContext, pull_rate
from rasl.graph.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.runtime import Runtime
from rasl.signal import Frame, MatrixPayload


class Source(BaseNode):
    """Writes a fresh (rows, 3) RGB frame every pull, or fills its port buffer when ``buffered``."""

    def __init__(self, node_id: str, rows: int, *, buffered: bool = False) -> None:
        self.id = node_id
        self.rows = rows
        self.buffered = buffered
        self.data = np.random.default_rng(0).random((rows, 3), dtype=np.float32)
        self.inputs = PortGroup.inputs()
        self.outputs = PortGroup.outputs(out=OutputPortSpec(RgbColorPayload))

    async def pull(self, tick: TickContext) -> None:
        """Write this tick's frame."""
        out = self.outputs.out
        if self.buffered:
            buf = out.acquire(self.rows)
            np.multiply(self.data, 1.0, out=buf)
            out.commit(Frame(topic=self.id, timestamp=tick.wall_time, payload=RgbColorPayload(buf)))
        else:
            out.write(Frame(topic=self.id, timestamp=tick.wall_time, payload=RgbColorPayload(self.data)))


class Pushed(BaseNode):
    """A push source: no pull; the benchmark commits to its port between ticks."""

    def __init__(self, node_id: str, rows: int) -> None:
        self.id = node_id
        self.rows = rows
        self.data = np.random.default_rng(0).random((rows, 3), dtype=np.float32)
        self.inputs = PortGroup.inputs()
        self.outputs = PortGroup.outputs(out=OutputPortSpec(RgbColorPayload))

    def push(self) -> None:
        """Commit one frame from outside a tick, as a background task would."""
        out = self.outputs.out
        buf = out.acquire(self.rows)
        np.multiply(self.data, 1.0, out=buf)
        out.commit(Frame(topic=self.id, timestamp=time.monotonic(), payload=RgbColorPayload(buf)))


class Forward(BaseNode):
    """Passes its input frame on unchanged."""

    def __init__(self, node_id: str) -> None:
        self.id = node_id
        self.inputs = PortGroup.inputs(**{"in": InputPortSpec(MatrixPayload)})
        self.outputs = PortGroup.outputs(out=OutputPortSpec(MatrixPayload))

    async def pull(self, tick: TickContext) -> None:
        """Forward the input frame, if any."""
        frame = self.inputs.get("in").read()
        if frame is not None:
            self.outputs.out.write(frame)


class Sink(BaseNode):
    """Drives the graph; touches one value of its input so the frame is really read."""

    def __init__(self, node_id: str = "sink", count: int | None = None) -> None:
        self.id = node_id
        self.inputs = PortGroup.inputs(**{"in": InputPortSpec(MatrixPayload, count=count)})
        self.outputs = PortGroup.outputs()
        self.total = 0.0

    @pull_rate(lambda self: 1000.0)
    async def pull(self, tick: TickContext) -> None:
        """Read the input."""
        frame = self.inputs.get("in").read()
        if frame is not None:
            self.total += float(np.asarray(frame.payload)[0, 0])


def _build(nodes, connect: Callable[[GraphBuilder], None]) -> ExecutionPlan:
    builder = GraphBuilder()
    for node in nodes:
        builder.add_node(node)
    connect(builder)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CycleWarning)
        return builder.build()


def fan_in() -> tuple[ExecutionPlan, list]:
    """16 sources of 32 RGB rows, sliced into one 512-row input."""
    sources = [Source(f"s{i}", 32) for i in range(16)]

    def connect(b: GraphBuilder) -> None:
        for i in range(16):
            b.connect(f"s{i}", "out", "sink", "in", None, Slice(32 * i, 32 * (i + 1)))

    return _build([*sources, Sink(count=512)], connect), []


def repeat() -> tuple[ExecutionPlan, list]:
    """A 10-row source repeated 50 times into one input."""
    return _build([Source("s", 10), Sink()], lambda b: b.connect("s", "out", "sink", "in", repeat=50)), []


def passthrough_chain() -> tuple[ExecutionPlan, list]:
    """A source through 20 forwarding nodes, every edge whole (passthrough)."""
    hops = [Forward(f"f{i}") for i in range(20)]

    def connect(b: GraphBuilder) -> None:
        b.connect("s", "out", "f0", "in")
        for i in range(19):
            b.connect(f"f{i}", "out", f"f{i + 1}", "in")
        b.connect("f19", "out", "sink", "in")

    return _build([Source("s", 170), *hops, Sink()], connect), []


def back_edge() -> tuple[ExecutionPlan, list]:
    """Two forwarding nodes in a cycle closed by a sliced back-edge, fed by a source."""

    def connect(b: GraphBuilder) -> None:
        b.connect("s", "out", "a", "in", None, Slice(0, 170))
        b.connect("a", "out", "b", "in")
        b.connect("b", "out", "a", "in", Slice(0, 170), Slice(170, 340))
        b.connect("b", "out", "sink", "in")

    return _build([Source("s", 170), Forward("a"), Forward("b"), Sink()], connect), []


def large_output() -> tuple[ExecutionPlan, list]:
    """One 512-row acquire/commit output, passed whole to the sink."""
    return _build([Source("s", 512, buffered=True), Sink()], lambda b: b.connect("s", "out", "sink", "in")), []


def push_4x() -> tuple[ExecutionPlan, list]:
    """A 170-row push source committing four times between ticks, sliced into the sink."""
    src = Pushed("s", 170)
    plan = _build([src, Sink()], lambda b: b.connect("s", "out", "sink", "in", Slice(0, 170)))
    return plan, [src] * 4


GRAPHS = {
    "fan_in_16x32": fan_in,
    "repeat_10x50": repeat,
    "passthrough_chain_20": passthrough_chain,
    "back_edge_sliced": back_edge,
    "large_output_512": large_output,
    "push_4x_per_tick": push_4x,
}


async def _time(make: Callable[[], tuple[ExecutionPlan, list]], ticks: int) -> float:
    """Microseconds per tick for one fresh runtime of the graph ``make`` builds."""
    plan, pushers = make()
    runtime = Runtime(plan)
    sinks = tuple(runtime._rate_drivers)
    async with anyio.create_task_group() as tg:
        runtime._host.attach(tg)
        runtime._host.bind_ports(plan)
        for node_id in plan.topological_order:
            await runtime._host.start(plan, node_id)
        t0 = time.monotonic()

        async def tick(i: int) -> None:
            for pusher in pushers:
                pusher.push()
            now = time.monotonic()
            await runtime._tick(TickContext(tick=i, t=now - t0, dt=0.001, wall_time=now), sinks)

        for i in range(200):  # warm-up: buffers allocated, coercions cached
            await tick(i)
        start = time.perf_counter()
        for i in range(200, 200 + ticks):
            await tick(i)
        elapsed = time.perf_counter() - start
        await runtime._host.stop_all(plan)
        tg.cancel_scope.cancel()
    return elapsed / ticks * 1e6


async def main(ticks: int, runs: int) -> None:
    """Print the median and spread of µs/tick for every graph."""
    print(f"{'graph':24} {'median µs/tick':>15} {'min':>8} {'max':>8}")
    for name, make in GRAPHS.items():
        samples = [await _time(make, ticks) for _ in range(runs)]
        print(f"{name:24} {statistics.median(samples):15.1f} {min(samples):8.1f} {max(samples):8.1f}")


if __name__ == "__main__":
    # Per-tick info logs (frame_interval_early, since ticks run back to back) would be timed too
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ticks", type=int, default=2000)
    parser.add_argument("--runs", type=int, default=7)
    args = parser.parse_args()
    anyio.run(main, args.ticks, args.runs)
