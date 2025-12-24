from __future__ import annotations

import numpy as np
import pytest

from rasl.engine.frames import (
    Frame,
    MatrixPayload,
    OkhslColorPayload,
    OklchColorPayload,
    RgbColorPayload,
)
from rasl.engine.tick import TickContext
from rasl.nodes.color.color_node import ColorNode


def _tick(*, tick: int = 0, t: float = 0.0, dt: float = 0.0, wall_time: float = 0.0) -> TickContext:
    return TickContext(tick=tick, t=t, dt=dt, wall_time=wall_time)


def _frame(payload, *, metadata=None) -> Frame:
    return Frame(topic="test", timestamp=0.0, payload=payload, metadata=metadata or {})


@pytest.mark.asyncio
async def test_color_node_respects_configured_model() -> None:
    node = ColorNode(ColorNode.Config(id="color", model="oklch"))
    data = np.array([[0.2, 0.4, 0.6]], dtype=np.float32)
    payload = RgbColorPayload(data)

    node.inputs.color._set_frame(_frame(payload))
    await node.pull(_tick())

    out = node.outputs.color._consume()
    assert out is not None
    assert isinstance(out.payload, OklchColorPayload)


@pytest.mark.asyncio
async def test_color_node_converts_to_config_when_input_is_color() -> None:
    node = ColorNode(ColorNode.Config(id="color", model="okhsl"))
    data = np.array([[0.1, 0.8, 0.3]], dtype=np.float32)
    payload = OklchColorPayload(data)

    node.inputs.color._set_frame(_frame(payload))
    await node.pull(_tick())

    out = node.outputs.color._consume()
    assert out is not None
    assert isinstance(out.payload, OkhslColorPayload)


@pytest.mark.asyncio
async def test_color_node_assumes_matrix_is_target_model() -> None:
    node = ColorNode(ColorNode.Config(id="color", model="srgb"))
    data = np.array([[0.063, 0.5, 0.9]], dtype=np.float32)
    payload = MatrixPayload(data)

    node.inputs.color._set_frame(_frame(payload))
    await node.pull(_tick())

    out = node.outputs.color._consume()
    assert out is not None
    assert isinstance(out.payload, RgbColorPayload)
    np.testing.assert_allclose(out.payload.data, data)
