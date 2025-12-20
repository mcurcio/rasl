from __future__ import annotations

import numpy as np
import pytest

from rasl.engine.frames import ColorPayload, Frame, MatrixPayload
from rasl.engine.tick import TickContext
from rasl.nodes.effects.matrix_multiply import MatrixMultiplyNode
from rasl.nodes.effects.range_map import RangeMapNode


def _frame(payload) -> Frame:
    return Frame(topic="test", timestamp=0.0, payload=payload)


def _tick() -> TickContext:
    return TickContext(tick=0, t=0.0, dt=0.0, wall_time=0.0)


@pytest.mark.asyncio
async def test_range_map_remaps_each_channel() -> None:
    node = RangeMapNode(
        RangeMapNode.Config(
            id="rm",
            ranges=((0.0, 1.0), (0.5, 1.5)),
            clamp=True,
        )
    )
    payload = MatrixPayload(
        np.array(
            [
                [0.0, 0.5],
                [1.5, 2.0],
            ],
            dtype=np.float32,
        )
    )

    node.inputs.input._set_frame(_frame(payload))
    await node.pull(_tick())

    out = node.outputs.out._consume()
    assert out is not None
    assert isinstance(out.payload, MatrixPayload)
    np.testing.assert_allclose(
        out.payload.data,
        np.array([[0.0, 0.0], [1.0, 1.0]], dtype=np.float32),
    )


@pytest.mark.asyncio
async def test_range_map_preserves_color_payload_type() -> None:
    node = RangeMapNode(
        RangeMapNode.Config(
            id="color_rm",
            ranges=((0.0, 1.0), (0.0, 1.0), (0.0, 1.0)),
        )
    )
    payload = ColorPayload(
        np.array([[0.2, 0.4, 0.6]], dtype=np.float32),
        model="srgb",
    )

    node.inputs.input._set_frame(_frame(payload))
    await node.pull(_tick())

    out = node.outputs.out._consume()
    assert out is not None
    assert isinstance(out.payload, ColorPayload)
    assert out.payload.model == "srgb"
    np.testing.assert_allclose(out.payload.data, payload.data)


@pytest.mark.asyncio
async def test_range_map_channel_mismatch_raises() -> None:
    node = RangeMapNode(
        RangeMapNode.Config(
            id="rm_error",
            ranges=((0.0, 1.0), (0.0, 1.0)),
        )
    )
    payload = ColorPayload(
        np.array([[0.1, 0.2, 0.3]], dtype=np.float32),
        model="srgb",
    )

    node.inputs.input._set_frame(_frame(payload))
    with pytest.raises(ValueError, match="payload has 3 channels"):
        await node.pull(_tick())


@pytest.mark.asyncio
async def test_matrix_multiply_applies_matrix() -> None:
    matrix = (
        (0.96409927, 0.02731212, 0.00858861),
        (0.00451189, 1.01313961, -0.01765150),
        (0.00899431, 0.01377757, 0.97722811),
    )
    node = MatrixMultiplyNode(MatrixMultiplyNode.Config(id="mm", matrix=matrix))
    payload = MatrixPayload(
        np.array([[0.5, 0.2, 0.1]], dtype=np.float32),
    )

    node.inputs.input._set_frame(_frame(payload))
    await node.pull(_tick())

    out = node.outputs.out._consume()
    assert out is not None
    assert isinstance(out.payload, MatrixPayload)
    expected = np.asarray(payload.data, dtype=np.float32) @ np.asarray(matrix, dtype=np.float32)
    np.testing.assert_allclose(out.payload.data, expected)


@pytest.mark.asyncio
async def test_matrix_multiply_preserves_color_payload_type() -> None:
    matrix = (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )
    node = MatrixMultiplyNode(MatrixMultiplyNode.Config(id="mm_color", matrix=matrix))
    payload = ColorPayload(
        np.array([[0.1, 0.3, 0.5]], dtype=np.float32),
        model="oklab",
    )

    node.inputs.input._set_frame(_frame(payload))
    await node.pull(_tick())

    out = node.outputs.out._consume()
    assert out is not None
    assert isinstance(out.payload, ColorPayload)
    assert out.payload.model == "oklab"
    np.testing.assert_allclose(out.payload.data, payload.data)


@pytest.mark.asyncio
async def test_matrix_multiply_channel_mismatch_raises() -> None:
    matrix = (
        (1.0, 0.0),
        (0.0, 1.0),
    )
    node = MatrixMultiplyNode(MatrixMultiplyNode.Config(id="mm_err", matrix=matrix))
    payload = MatrixPayload(np.array([[0.1, 0.2, 0.3]], dtype=np.float32))

    node.inputs.input._set_frame(_frame(payload))
    with pytest.raises(ValueError, match="payload has 3 channels"):
        await node.pull(_tick())
