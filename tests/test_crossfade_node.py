from __future__ import annotations

import numpy as np
import pytest

from rasl.engine.frames import BoolPayload, ColorPayload, Frame
from rasl.engine.tick import TickContext
from rasl.nodes.effects.crossfade import CrossfadeNode


def _tick(*, tick: int = 0, t: float = 0.0, dt: float = 0.0, wall_time: float = 0.0) -> TickContext:
    return TickContext(tick=tick, t=t, dt=dt, wall_time=wall_time)


def _frame(payload) -> Frame:
    return Frame(topic="test", timestamp=0.0, payload=payload)


@pytest.mark.asyncio
async def test_crossfade_initial_false_outputs_input0() -> None:
    node = CrossfadeNode(CrossfadeNode.Config(id="x", seconds=1.0))

    c0 = ColorPayload(np.array([[0.1, 0.2, 0.3]], dtype=np.float32), model="hsl")
    c1 = ColorPayload(np.array([[0.9, 0.8, 0.7]], dtype=np.float32), model="hsl")

    node.inputs.input0._set_frame(_frame(c0))
    node.inputs.input1._set_frame(_frame(c1))
    node.inputs.selector._set_frame(_frame(BoolPayload(np.array([[0]], dtype=np.float32))))

    await node.pull(_tick(dt=0.1))

    out = node.outputs.out._consume()
    assert out is not None
    assert isinstance(out.payload, ColorPayload)
    assert out.payload.model == "hsl"
    np.testing.assert_allclose(np.asarray(out.payload), np.asarray(c0))


@pytest.mark.asyncio
async def test_crossfade_initial_true_outputs_input1() -> None:
    node = CrossfadeNode(CrossfadeNode.Config(id="x", seconds=1.0))

    c0 = ColorPayload(np.array([[0.1, 0.2, 0.3]], dtype=np.float32), model="hsl")
    c1 = ColorPayload(np.array([[0.9, 0.8, 0.7]], dtype=np.float32), model="hsl")

    node.inputs.input0._set_frame(_frame(c0))
    node.inputs.input1._set_frame(_frame(c1))
    node.inputs.selector._set_frame(_frame(BoolPayload(np.array([[1]], dtype=np.float32))))

    await node.pull(_tick(dt=0.1))

    out = node.outputs.out._consume()
    assert out is not None
    assert isinstance(out.payload, ColorPayload)
    assert out.payload.model == "hsl"
    np.testing.assert_allclose(np.asarray(out.payload), np.asarray(c1))


@pytest.mark.asyncio
async def test_crossfade_progresses_over_seconds() -> None:
    node = CrossfadeNode(CrossfadeNode.Config(id="x", seconds=1.0))

    c0 = ColorPayload(np.array([[0.0, 0.0, 0.0]], dtype=np.float32), model="hsl")
    c1 = ColorPayload(np.array([[0.5, 1.0, 1.0]], dtype=np.float32), model="hsl")

    node.inputs.input0._set_frame(_frame(c0))
    node.inputs.input1._set_frame(_frame(c1))

    # Start at false
    node.inputs.selector._set_frame(_frame(BoolPayload(np.array([[0]], dtype=np.float32))))
    await node.pull(_tick(dt=0.1))
    node.outputs.out._consume()

    # Switch true: after 0.5s we should be halfway
    node.inputs.selector._set_frame(_frame(BoolPayload(np.array([[1]], dtype=np.float32))))
    await node.pull(_tick(dt=0.5))
    out = node.outputs.out._consume()
    assert out is not None
    np.testing.assert_allclose(np.asarray(out.payload), np.array([[0.75, 0.5, 0.5]], dtype=np.float32))

    # Another 0.5s should reach fully true
    await node.pull(_tick(dt=0.5))
    out = node.outputs.out._consume()
    assert out is not None
    np.testing.assert_allclose(np.asarray(out.payload), np.asarray(c1))


@pytest.mark.asyncio
async def test_crossfade_seconds_zero_is_instant() -> None:
    node = CrossfadeNode(CrossfadeNode.Config(id="x", seconds=0.0))

    c0 = ColorPayload(np.array([[0.2, 0.2, 0.2]], dtype=np.float32), model="hsl")
    c1 = ColorPayload(np.array([[0.8, 0.8, 0.8]], dtype=np.float32), model="hsl")

    node.inputs.input0._set_frame(_frame(c0))
    node.inputs.input1._set_frame(_frame(c1))

    node.inputs.selector._set_frame(_frame(BoolPayload(np.array([[0]], dtype=np.float32))))
    await node.pull(_tick(dt=0.1))
    node.outputs.out._consume()

    node.inputs.selector._set_frame(_frame(BoolPayload(np.array([[1]], dtype=np.float32))))
    await node.pull(_tick(dt=0.0001))

    out = node.outputs.out._consume()
    assert out is not None
    np.testing.assert_allclose(np.asarray(out.payload), np.asarray(c1))


@pytest.mark.asyncio
async def test_crossfade_hue_wrap_shortest_path() -> None:
    node = CrossfadeNode(CrossfadeNode.Config(id="x", seconds=1.0))

    # Hue should travel shortest path: 0.1 -> 0.9 goes "backwards" across wrap.
    c0 = ColorPayload(np.array([[0.1, 0.5, 0.5]], dtype=np.float32), model="hsl")
    c1 = ColorPayload(np.array([[0.9, 0.5, 0.5]], dtype=np.float32), model="hsl")

    node.inputs.input0._set_frame(_frame(c0))
    node.inputs.input1._set_frame(_frame(c1))

    node.inputs.selector._set_frame(_frame(BoolPayload(np.array([[0]], dtype=np.float32))))
    await node.pull(_tick(dt=0.0))
    node.outputs.out._consume()

    # Halfway (mix=0.5) should wrap to 0.0, not 0.5.
    node.inputs.selector._set_frame(_frame(BoolPayload(np.array([[1]], dtype=np.float32))))
    await node.pull(_tick(dt=0.5))

    out = node.outputs.out._consume()
    assert out is not None
    arr = np.asarray(out.payload)
    # Hue can land at 1.0 instead of 0.0 due to float modulo when the value is a tiny negative.
    hue = float(arr.reshape(-1)[0])
    assert min(abs(hue - 0.0), abs(hue - 1.0)) <= 1e-6
    np.testing.assert_allclose(arr[:, 1:], np.array([[0.5, 0.5]], dtype=np.float32), atol=1e-6)


@pytest.mark.asyncio
async def test_crossfade_count_mismatch_is_error() -> None:
    node = CrossfadeNode(CrossfadeNode.Config(id="x", seconds=0.0))

    c0 = ColorPayload(np.array([[0.1, 0.2, 0.3]], dtype=np.float32), model="hsl")
    c1 = ColorPayload(
        np.array([[0.9, 0.8, 0.7], [0.8, 0.7, 0.6]], dtype=np.float32), model="hsl"
    )

    node.inputs.input0._set_frame(_frame(c0))
    node.inputs.input1._set_frame(_frame(c1))
    node.inputs.selector._set_frame(_frame(BoolPayload(np.array([[1]], dtype=np.float32))))

    with pytest.raises(ValueError, match="matching count"):
        await node.pull(_tick(dt=0.1))
