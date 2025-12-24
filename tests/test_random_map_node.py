from __future__ import annotations

import numpy as np
import pytest

from rasl.engine.frames import ColorPayload, Frame, MatrixPayload
from rasl.engine.tick import TickContext
from rasl.nodes.effects.random_map import RandomMapNode


def _frame(payload) -> Frame:
    return Frame(topic="test", timestamp=0.0, payload=payload)


def _tick() -> TickContext:
    return TickContext(tick=0, t=0.0, dt=0.0, wall_time=0.0)


@pytest.mark.asyncio
async def test_random_map_preserves_mapping_between_frames() -> None:
    node = RandomMapNode(RandomMapNode.Config(id="rm", seed=1234))
    payload = MatrixPayload(np.array([[1.0], [2.0], [3.0], [4.0]], dtype=np.float32))

    node.inputs.input._set_frame(_frame(payload))
    await node.pull(_tick())
    out = node.outputs.out._consume()
    assert out is not None

    mapping = node._mapping
    assert mapping is not None

    payload2 = MatrixPayload(np.array([[10.0], [20.0], [30.0], [40.0]], dtype=np.float32))
    node.inputs.input._set_frame(_frame(payload2))
    await node.pull(_tick())
    out2 = node.outputs.out._consume()
    assert out2 is not None
    np.testing.assert_allclose(out2.payload.data, payload2.data[mapping])


@pytest.mark.asyncio
async def test_random_map_channel_override() -> None:
    node = RandomMapNode(RandomMapNode.Config(id="rm_override", channel_count=2, seed=5))
    payload = MatrixPayload(
        np.array(
            [
                [0.0, 1.0],
                [2.0, 3.0],
                [4.0, 5.0],
                [6.0, 7.0],
            ],
            dtype=np.float32,
        )
    )

    node.inputs.input._set_frame(_frame(payload))
    await node.pull(_tick())
    out = node.outputs.out._consume()
    assert out is not None
    assert out.payload.data.shape == (2, 2)

    mapping = node._mapping
    assert mapping is not None
    np.testing.assert_allclose(out.payload.data, payload.data[mapping])


@pytest.mark.asyncio
async def test_random_map_detects_input_channel_change() -> None:
    node = RandomMapNode(RandomMapNode.Config(id="rm_change"))

    payload = MatrixPayload(np.array([[0.0, 1.0]], dtype=np.float32))
    node.inputs.input._set_frame(_frame(payload))
    await node.pull(_tick())
    assert node.outputs.out._consume() is not None

    payload_mismatch = MatrixPayload(np.array([[0.0, 1.0], [2.0, 3.0]], dtype=np.float32))
    node.inputs.input._set_frame(_frame(payload_mismatch))
    with pytest.raises(ValueError, match="input channel count changed"):
        await node.pull(_tick())


@pytest.mark.asyncio
async def test_random_map_preserves_color_payload_type() -> None:
    node = RandomMapNode(RandomMapNode.Config(id="rm_color", seed=99))
    payload = ColorPayload(
        np.array([[0.1, 0.4, 0.7]], dtype=np.float32),
        model="srgb",
    )

    node.inputs.input._set_frame(_frame(payload))
    await node.pull(_tick())

    out = node.outputs.out._consume()
    assert out is not None
    assert isinstance(out.payload, ColorPayload)
    assert out.payload.model == "srgb"
