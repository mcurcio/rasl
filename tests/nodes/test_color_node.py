from __future__ import annotations

import numpy as np
import pytest

from rasl.color import OkhslColorPayload, OklchColorPayload, RgbColorPayload
from rasl.graph.node import TickContext
from rasl.nodes.color.color_node import ColorNode
from rasl.signal import Frame, MatrixPayload


def _tick(*, tick: int = 0, t: float = 0.0, dt: float = 0.0, wall_time: float = 0.0) -> TickContext:
    return TickContext(tick=tick, t=t, dt=dt, wall_time=wall_time)


def _frame(payload, *, metadata=None) -> Frame:
    return Frame(topic="test", timestamp=0.0, payload=payload, metadata=metadata or {})


@pytest.mark.asyncio
async def test_color_node_respects_configured_model() -> None:
    node = ColorNode(ColorNode.Config(id="color", model="oklch"))
    data = np.array([[0.2, 0.4, 0.6]], dtype=np.float32)
    payload = RgbColorPayload(data)

    node.inputs.color._write(_frame(payload))
    await node.pull(_tick())

    out = node.outputs.color._publish()
    assert out is not None
    assert isinstance(out.payload, OklchColorPayload)


@pytest.mark.asyncio
async def test_color_node_converts_to_config_when_input_is_color() -> None:
    node = ColorNode(ColorNode.Config(id="color", model="okhsl"))
    data = np.array([[0.1, 0.8, 0.3]], dtype=np.float32)
    payload = OklchColorPayload(data)

    node.inputs.color._write(_frame(payload))
    await node.pull(_tick())

    out = node.outputs.color._publish()
    assert out is not None
    assert isinstance(out.payload, OkhslColorPayload)


@pytest.mark.asyncio
async def test_color_node_assumes_matrix_is_target_model() -> None:
    node = ColorNode(ColorNode.Config(id="color", model="srgb"))
    data = np.array([[0.063, 0.5, 0.9]], dtype=np.float32)
    payload = MatrixPayload(data)

    node.inputs.color._write(_frame(payload))
    await node.pull(_tick())

    out = node.outputs.color._publish()
    assert out is not None
    assert isinstance(out.payload, RgbColorPayload)
    np.testing.assert_allclose(out.payload.data, data)


@pytest.mark.asyncio
async def test_color_node_rgb_is_srgb() -> None:
    """``node Color x rgb`` emits sRGB; linear light is asked for as ``linear``."""
    from rasl.color import LinearRgbColorPayload, RgbColorPayload

    pixels = np.array([[1.0, 0.5, 0.25]], dtype=np.float32)
    for model, expected_class in (("rgb", RgbColorPayload), ("linear", LinearRgbColorPayload)):
        node = ColorNode(ColorNode.Config(id="color", model=model))
        node.inputs.color._write(Frame(topic="t", timestamp=0.0, payload=RgbColorPayload(pixels)))
        await node.pull(_tick())
        out = node.outputs.color._publish().payload
        assert type(out) is expected_class
        if model == "rgb":
            np.testing.assert_allclose(out.data, pixels, atol=1e-6)
        else:
            np.testing.assert_allclose(out.data, [[1.0, 0.214, 0.0508]], atol=1e-3)


async def test_color_node_does_not_pass_on_its_inputs_array() -> None:
    node = ColorNode(ColorNode.Config(id="color", model="srgb"))
    for payload in (
        RgbColorPayload(np.full((2, 3), 0.5, dtype=np.float32)),  # already the target type
        MatrixPayload(np.full((2, 3), 0.5, dtype=np.float32)),  # wrapped, not converted
    ):
        node.inputs.color._write(_frame(payload))
        await node.pull(_tick())
        out = node.outputs.color._publish()
        assert np.asarray(out.payload).tolist() == np.asarray(payload).tolist()
        assert not np.shares_memory(np.asarray(out.payload), np.asarray(payload))
