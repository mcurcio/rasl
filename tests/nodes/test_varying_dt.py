"""Stateful nodes give the same output over a span of time however often they are pulled.

A node shared by sinks of different rates is pulled at the union of their times, so its dt
varies from pull to pull (owner, 2026-11-14; rasl-pd0.38). Each node here is pulled across
half a second at 20 Hz, at 30 Hz, and at the uneven mix of both, and must end in one place.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pytest

from rasl.color import ColorPayload, RgbColorPayload
from rasl.graph.node import BaseNode, TickContext
from rasl.nodes.effects.crossfade import CrossfadeNode
from rasl.nodes.effects.smooth import SmoothNode
from rasl.nodes.effects.twinkle import TwinkleEffectNode
from rasl.nodes.effects.waveform import WaveformNode
from rasl.signal import BoolPayload, Frame, MatrixPayload

SPAN_S = 0.5


def _times(*rates_hz: int) -> list[float]:
    """Every due time of the given rates in [0, SPAN_S], in order, each once."""
    times = {round(n / hz, 9) for hz in rates_hz for n in range(int(SPAN_S * hz) + 1)}
    return sorted(times)


SCHEDULES = {"20 Hz": _times(20), "30 Hz": _times(30), "20 and 30 Hz": _times(20, 30)}


def _frame(payload: object) -> Frame:
    return Frame(topic="test", timestamp=0.0, payload=payload)


def _matrix(*values: float) -> Frame:
    return _frame(MatrixPayload(np.asarray(values, dtype=np.float32).reshape(-1, 1)))


def _hsl(h: float, s: float, l: float) -> Frame:
    return _frame(ColorPayload(np.array([[h, s, l]], dtype=np.float32), model="hsl"))


def _crossfade() -> tuple[BaseNode, Callable[[BaseNode, float], None], str]:
    """A 1 s fade whose selector turns true after the first pull: half way at 0.5 s."""
    node = CrossfadeNode(CrossfadeNode.Config(id="x", seconds=1.0))

    def feed(node: BaseNode, t: float) -> None:
        node.inputs.input0._write(_hsl(0.0, 0.2, 0.2))
        node.inputs.input1._write(_hsl(0.4, 0.8, 0.6))
        node.inputs.selector._write(_frame(BoolPayload(np.array([[t > 0.0]], dtype=np.bool_))))

    return node, feed, "out"


def _smooth(**settings: str) -> Callable[[], tuple[BaseNode, Callable[[BaseNode, float], None], str]]:
    def make() -> tuple[BaseNode, Callable[[BaseNode, float], None], str]:
        node = SmoothNode(SmoothNode.Config(id="s", **settings))

        def feed(node: BaseNode, t: float) -> None:
            node.inputs.input._write(_matrix(0.0, 0.0) if t == 0.0 else _matrix(1.0, 0.5))

        return node, feed, "output"

    return make


def _twinkle() -> tuple[BaseNode, Callable[[BaseNode, float], None], str]:
    node = TwinkleEffectNode(TwinkleEffectNode.Config(id="t", frequency_hz=1.0))

    def feed(node: BaseNode, t: float) -> None:
        node.inputs.input._write(_frame(RgbColorPayload(np.ones((4, 3), dtype=np.float32))))

    return node, feed, "out"


def _waveform() -> tuple[BaseNode, Callable[[BaseNode, float], None], str]:
    node = WaveformNode(WaveformNode.Config(id="w", shape="sine", frequency_hz=0.7, output_channels=3))
    return node, lambda node, t: None, "out"


NODES = {
    "Crossfade": _crossfade,
    "Smooth (smooth_period)": _smooth(smooth_period="200ms"),
    "Smooth (slew_period)": _smooth(smooth_period="0ms", slew_period="2s"),
    "TwinkleEffect": _twinkle,
    "Waveform": _waveform,
}


async def _final_output(make: Callable[[], tuple], times: list[float]) -> np.ndarray:
    node, feed, port = make()
    previous = 0.0
    out = None
    for n, t in enumerate(times):
        feed(node, t)
        await node.pull(TickContext(tick=n, t=t, dt=t - previous, wall_time=t))
        out = node.outputs.get(port)._publish()
        previous = t
    assert out is not None
    return np.asarray(getattr(out.payload, "data", out.payload), dtype=np.float64).copy()


@pytest.mark.parametrize("name", list(NODES))
async def test_the_output_after_half_a_second_does_not_depend_on_the_pull_rate(name: str) -> None:
    results = {label: await _final_output(NODES[name], times) for label, times in SCHEDULES.items()}
    reference = results["20 Hz"]
    for label, result in results.items():
        np.testing.assert_allclose(result, reference, atol=1e-4, err_msg=f"{name} at {label}")


async def test_the_fade_and_the_filters_have_moved_but_not_arrived() -> None:
    """Guards the test above: a node that ignored dt, or jumped, would also agree with itself."""
    fade = await _final_output(_crossfade, SCHEDULES["20 Hz"])
    np.testing.assert_allclose(fade, [[0.2, 0.5, 0.4]], atol=1e-4)  # half way from input0 to input1
    smooth = await _final_output(NODES["Smooth (smooth_period)"], SCHEDULES["30 Hz"])
    np.testing.assert_allclose(smooth[0, 0], 1.0 - np.exp(-SPAN_S / 0.2), atol=1e-4)
    slew = await _final_output(NODES["Smooth (slew_period)"], SCHEDULES["20 and 30 Hz"])
    np.testing.assert_allclose(slew[:, 0], [0.25, 0.25], atol=1e-4)  # 0.5 s of a 2 s full-scale slew
