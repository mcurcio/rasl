from __future__ import annotations

import math

import numpy as np
import pytest

from rasl.color import ColorPayload
from rasl.graph.node import TickContext
from rasl.nodes.effects.smooth import SmoothNode
from rasl.signal import BoolPayload, Frame, MatrixPayload


def _frame(payload) -> Frame:
    return Frame(topic="test", timestamp=0.0, payload=payload)


def _tick(dt: float) -> TickContext:
    return TickContext(tick=0, t=0.0, dt=dt, wall_time=0.0)


@pytest.mark.asyncio
async def test_smooth_passes_through_first_frame() -> None:
    node = SmoothNode(SmoothNode.Config(id="smooth"))
    payload = MatrixPayload(np.array([[0.25], [0.75]], dtype=np.float32))

    node.inputs.input._set_frame(_frame(payload))
    await node.pull(_tick(0.0))

    out = node.outputs.output._consume()
    assert out is not None
    np.testing.assert_allclose(out.payload.data, payload.data)


@pytest.mark.asyncio
async def test_smooth_applies_exponential_average() -> None:
    node = SmoothNode(
        SmoothNode.Config(
            id="smooth",
            smooth_period="100ms",
            bypass_epsilon=0.0,
        )
    )

    base = MatrixPayload(np.array([[0.0]], dtype=np.float32))
    node.inputs.input._set_frame(_frame(base))
    await node.pull(_tick(0.0))
    _ = node.outputs.output._consume()

    target = MatrixPayload(np.array([[1.0]], dtype=np.float32))
    node.inputs.input._set_frame(_frame(target))
    dt = 0.05  # 50 ms
    await node.pull(_tick(dt))

    out = node.outputs.output._consume()
    assert out is not None

    tau = 0.1  # seconds
    alpha = 1.0 - math.exp(-dt / tau)
    expected = np.array([[alpha]], dtype=np.float32)
    np.testing.assert_allclose(out.payload.data, expected, atol=1e-6)


@pytest.mark.asyncio
async def test_smooth_slew_period_limits_how_fast_a_value_moves() -> None:
    # A full-scale change may take no less than 2 s: 0.1 s allows a move of 0.05
    node = SmoothNode(SmoothNode.Config(id="smooth", smooth_period="0ms", slew_period="2s"))

    start = MatrixPayload(np.array([[0.0]], dtype=np.float32))
    node.inputs.input._set_frame(_frame(start))
    await node.pull(_tick(0.0))
    _ = node.outputs.output._consume()

    jump = MatrixPayload(np.array([[1.0]], dtype=np.float32))
    node.inputs.input._set_frame(_frame(jump))
    await node.pull(_tick(0.1))

    out = node.outputs.output._consume()
    assert out is not None
    np.testing.assert_allclose(out.payload.data, np.array([[0.05]], dtype=np.float32), atol=1e-6)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "steps",
    [
        [1 / 20] * 20,
        [1 / 30] * 30,
        [1 / 30, 1 / 60, 1 / 60, 1 / 30] * 10,  # shared by a 30 Hz and a 20 Hz sink
        [1.0],
    ],
)
async def test_smooth_slew_does_not_depend_on_the_pull_rate(steps: list[float]) -> None:
    node = SmoothNode(SmoothNode.Config(id="smooth", smooth_period="0ms", slew_period="4s"))

    node.inputs.input._set_frame(_frame(MatrixPayload(np.array([[0.0]], dtype=np.float32))))
    await node.pull(_tick(0.0))
    _ = node.outputs.output._consume()

    node.inputs.input._set_frame(_frame(MatrixPayload(np.array([[1.0]], dtype=np.float32))))
    out = None
    for dt in steps:
        await node.pull(_tick(dt))
        out = node.outputs.output._consume()

    # One second into a four-second full-scale fade, however it was stepped
    assert out is not None
    np.testing.assert_allclose(out.payload.data, np.array([[0.25]], dtype=np.float32), atol=1e-5)


@pytest.mark.asyncio
@pytest.mark.parametrize("steps", [[1 / 20] * 20, [1 / 30, 1 / 60, 1 / 60, 1 / 30] * 10, [1.0]])
async def test_smooth_period_does_not_depend_on_the_pull_rate(steps: list[float]) -> None:
    node = SmoothNode(SmoothNode.Config(id="smooth", smooth_period="500ms"))

    node.inputs.input._set_frame(_frame(MatrixPayload(np.array([[0.0]], dtype=np.float32))))
    await node.pull(_tick(0.0))
    _ = node.outputs.output._consume()

    node.inputs.input._set_frame(_frame(MatrixPayload(np.array([[1.0]], dtype=np.float32))))
    out = None
    for dt in steps:
        await node.pull(_tick(dt))
        out = node.outputs.output._consume()

    assert out is not None
    np.testing.assert_allclose(out.payload.data, [[1 - np.exp(-2.0)]], atol=1e-5)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("slew_period", "-1s", "a duration cannot be negative"),
        ("smooth_period", 30, "a duration needs a unit, such as 30ms or 30s"),
        ("smooth_period", "30hz", "a duration takes a time, such as 50ms or 2s, not a frequency"),
    ],
)
def test_smooth_periods_are_durations(field: str, value, message: str) -> None:
    with pytest.raises(ValueError, match=message) as caught:
        SmoothNode.Config(id="smooth", **{field: value})
    assert field in str(caught.value)


@pytest.mark.asyncio
async def test_smooth_reset_bypasses_accumulator() -> None:
    node = SmoothNode(SmoothNode.Config(id="smooth", smooth_period="200ms"))

    start = MatrixPayload(np.array([[0.0]], dtype=np.float32))
    node.inputs.input._set_frame(_frame(start))
    await node.pull(_tick(0.0))
    _ = node.outputs.output._consume()

    mid = MatrixPayload(np.array([[0.5]], dtype=np.float32))
    node.inputs.input._set_frame(_frame(mid))
    await node.pull(_tick(0.05))
    _ = node.outputs.output._consume()

    reset_payload = BoolPayload(np.array([[1.0]], dtype=np.float32))
    target = MatrixPayload(np.array([[0.9]], dtype=np.float32))
    node.inputs.input._set_frame(_frame(target))
    node.inputs.reset._set_frame(_frame(reset_payload))
    await node.pull(_tick(0.05))

    out = node.outputs.output._consume()
    assert out is not None
    np.testing.assert_allclose(out.payload.data, target.data)


@pytest.mark.asyncio
async def test_smooth_preserves_color_payload_type() -> None:
    node = SmoothNode(SmoothNode.Config(id="smooth", smooth_period="50ms"))
    first = ColorPayload(np.array([[0.1, 0.2, 0.3]], dtype=np.float32), model="srgb")

    node.inputs.input._set_frame(_frame(first))
    await node.pull(_tick(0.0))
    _ = node.outputs.output._consume()

    second = ColorPayload(np.array([[0.3, 0.4, 0.5]], dtype=np.float32), model="srgb")
    node.inputs.input._set_frame(_frame(second))
    await node.pull(_tick(0.05))

    out = node.outputs.output._consume()
    assert out is not None
    assert isinstance(out.payload, ColorPayload)
    assert out.payload.model == "srgb"
