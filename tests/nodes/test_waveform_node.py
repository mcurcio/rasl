"""WaveformNode, pulled as the runtime pulls it."""

from __future__ import annotations

import numpy as np
import pytest

from rasl.graph.node import TickContext
from rasl.nodes.effects.waveform import WaveformNode
from rasl.signal import Frame, MatrixPayload


def _column(values) -> Frame:
    data = np.asarray(values, dtype=np.float32).reshape(-1, 1)
    return Frame(topic="test", timestamp=0.0, payload=MatrixPayload(data))


async def _pull(node: WaveformNode, t: float) -> np.ndarray:
    await node.pull(TickContext(tick=0, t=t, dt=0.0, wall_time=t))
    return np.asarray(node.outputs.out._consume().payload).reshape(-1).copy()


def _sawtooth(channels: int = 2) -> WaveformNode:
    return WaveformNode(WaveformNode.Config(id="w", shape="sawtooth", frequency_hz=1.0, output_channels=channels))


async def test_a_sawtooth_is_the_phase() -> None:
    np.testing.assert_allclose(await _pull(_sawtooth(), 0.25), [0.25, 0.25], atol=1e-6)


async def test_a_phase_input_offsets_each_channel() -> None:
    node = _sawtooth(4)
    node.inputs.phase._set_frame(_column([0.0, 0.25, 0.5, 0.75]))  # used to raise: (N,1) against (N,)
    np.testing.assert_allclose(await _pull(node, 0.1), [0.1, 0.35, 0.6, 0.85], atol=1e-6)


async def test_a_speed_input_scales_each_channel() -> None:
    node = _sawtooth(2)
    node.inputs.speed._set_frame(_column([1.0, 2.0]))
    np.testing.assert_allclose(await _pull(node, 0.2), [0.2, 0.4], atol=1e-6)


@pytest.mark.parametrize(("t", "expected"), [(0.99, 0.485), (1.0, 0.5), (1.5, 0.25), (2.0, 0.0)])
async def test_a_fractional_speed_does_not_jump_when_the_base_cycle_restarts(t: float, expected: float) -> None:
    node = _sawtooth(1)
    node.inputs.speed._set_frame(_column([1.5]))
    assert (await _pull(node, t)).item() == pytest.approx(expected, abs=1e-5)


async def test_fewer_modulation_values_than_channels_repeat() -> None:
    node = _sawtooth(4)
    node.inputs.phase._set_frame(_column([0.0, 0.5]))
    np.testing.assert_allclose(await _pull(node, 0.1), [0.1, 0.6, 0.1, 0.6], atol=1e-6)
