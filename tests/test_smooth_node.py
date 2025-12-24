from __future__ import annotations

import math

import numpy as np
import pytest

from rasl.engine.frames import BoolPayload, ColorPayload, Frame, MatrixPayload
from rasl.engine.tick import TickContext
from rasl.nodes.effects.smooth import SmoothNode


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
async def test_smooth_respects_max_delta() -> None:
    node = SmoothNode(
        SmoothNode.Config(
            id="smooth",
            smooth_period="0ms",
            max_delta=0.1,
        )
    )

    start = MatrixPayload(np.array([[0.0]], dtype=np.float32))
    node.inputs.input._set_frame(_frame(start))
    await node.pull(_tick(0.0))
    _ = node.outputs.output._consume()

    jump = MatrixPayload(np.array([[1.0]], dtype=np.float32))
    node.inputs.input._set_frame(_frame(jump))
    await node.pull(_tick(0.016))

    out = node.outputs.output._consume()
    assert out is not None
    np.testing.assert_allclose(out.payload.data, np.array([[0.1]], dtype=np.float32))


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
