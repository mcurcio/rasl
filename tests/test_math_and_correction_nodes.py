"""MathNode and ColorCorrectionNode, pulled as the scheduler pulls them."""

from __future__ import annotations

import numpy as np
import pytest

from rasl.color import HsbkColorPayload, LinearRgbColorPayload, RgbColorPayload
from rasl.graph.node import TickContext
from rasl.nodes.color.correction_node import ColorCorrectionNode
from rasl.nodes.effects.math import MathNode
from rasl.signal import Frame, MatrixPayload

TICK = TickContext(tick=0, t=0.0, dt=0.0, wall_time=0.0)


def _frame(payload) -> Frame:
    return Frame(topic="test", timestamp=0.0, payload=payload)


def _matrix(values) -> Frame:
    return _frame(MatrixPayload(np.asarray(values, dtype=np.float32)))


async def _math(a=None, b=None, **config) -> np.ndarray | None:
    node = MathNode(MathNode.Config(id="m", **config))
    node.inputs.a._set_frame(None if a is None else _matrix(a))
    node.inputs.b._set_frame(None if b is None else _matrix(b))
    await node.pull(TICK)
    out = node.outputs.out._consume()
    node.inputs.a._clear()
    node.inputs.b._clear()
    return None if out is None else np.asarray(out.payload)


class TestMathNodePull:
    async def test_two_inputs_of_one_shape(self) -> None:
        out = await _math([[0.2], [0.4]], [[0.5], [0.5]], operation="multiply")
        np.testing.assert_allclose(out, [[0.1], [0.2]], atol=1e-6)

    async def test_a_constant_stands_in_for_a_missing_input(self) -> None:
        out = await _math([[0.2, 0.4], [0.6, 0.8]], operation="multiply", constant_b=0.5)
        np.testing.assert_allclose(out, [[0.1, 0.2], [0.3, 0.4]], atol=1e-6)

    async def test_one_column_is_applied_to_every_column(self) -> None:
        out = await _math([[0.2, 0.4, 0.6], [1.0, 1.0, 1.0]], [[0.5], [0.1]], operation="multiply")
        np.testing.assert_allclose(out, [[0.1, 0.2, 0.3], [0.1, 0.1, 0.1]], atol=1e-6)

    async def test_a_shorter_input_repeats_to_fill_the_longer(self) -> None:
        out = await _math([[0.1], [0.2], [0.3], [0.4]], [[1.0], [0.5]], operation="multiply")
        np.testing.assert_allclose(out, [[0.1], [0.1], [0.3], [0.2]], atol=1e-6)

    async def test_the_result_is_clamped_unless_told_otherwise(self) -> None:
        assert (await _math([[0.8]], [[0.7]], operation="add")).item() == pytest.approx(1.0)
        assert (await _math([[0.8]], [[0.7]], operation="add", clamp=False)).item() == pytest.approx(1.5)

    async def test_no_input_writes_nothing(self) -> None:
        assert await _math(operation="add", constant_b=0.5) is None


async def _correct(payload, **config):
    node = ColorCorrectionNode(ColorCorrectionNode.Config(id="c", **config))
    node.inputs.input._set_frame(_frame(payload))
    await node.pull(TICK)
    out = node.outputs.out._consume()
    node.inputs.input._clear()
    return out.payload


class TestColorCorrectionPull:
    @pytest.mark.parametrize("pixels", [1, 2, 3, 7])
    async def test_any_number_of_pixels(self, pixels: int) -> None:
        data = np.full((pixels, 3), 0.5, dtype=np.float32)
        out = await _correct(LinearRgbColorPayload(data), gamma=2.0)
        assert isinstance(out, RgbColorPayload)
        np.testing.assert_allclose(out.data, np.full((pixels, 3), 0.5**0.5), atol=1e-5)

    async def test_channel_scale_and_brightness_apply_in_linear_light(self) -> None:
        data = np.array([[0.8, 0.8, 0.8], [0.2, 0.4, 0.6]], dtype=np.float32)
        out = await _correct(
            LinearRgbColorPayload(data), gamma=1.0, r_scale=0.5, g_scale=1.0, b_scale=0.25, brightness=0.5
        )
        np.testing.assert_allclose(out.data, data * [0.5, 1.0, 0.25] * 0.5, atol=1e-6)

    async def test_saturation_zero_gives_grey_at_the_pixel_luminance(self) -> None:
        data = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
        out = await _correct(LinearRgbColorPayload(data), gamma=1.0, saturation=0.0)
        np.testing.assert_allclose(out.data, [[0.2126, 0.2126, 0.2126]], atol=1e-6)

    async def test_srgb_input_is_linearised_first(self) -> None:
        srgb = RgbColorPayload(np.array([[0.5, 0.5, 0.5]], dtype=np.float32))
        linear = srgb.to_model(LinearRgbColorPayload).data
        out = await _correct(srgb, gamma=1.0)
        np.testing.assert_allclose(out.data, linear, atol=1e-6)

    async def test_a_plain_matrix_of_triplets_is_read_as_srgb(self) -> None:
        data = np.array([[0.5, 0.5, 0.5], [1.0, 0.0, 0.0]], dtype=np.float32)
        from_matrix = await _correct(MatrixPayload(data), gamma=2.2)
        from_srgb = await _correct(RgbColorPayload(data), gamma=2.2)
        np.testing.assert_allclose(from_matrix.data, from_srgb.data, atol=1e-6)

    async def test_a_matrix_that_is_not_triplets_passes_through(self) -> None:
        payload = MatrixPayload(np.array([[0.1, 0.2]], dtype=np.float32))
        assert await _correct(payload) is payload

    async def test_a_four_component_model_is_converted(self) -> None:
        hsbk = HsbkColorPayload(np.array([[0.0, 1.0, 1.0, 0.5]], dtype=np.float32))
        out = await _correct(hsbk, gamma=1.0)
        assert out.data.shape == (1, 3)
        assert out.data[0, 0] == pytest.approx(1.0, abs=1e-3)


class TestSacnSinkPull:
    """The sACN sink is pulled at its own rate and hands the sender one universe."""

    class _Output:
        dmx_data: tuple[int, ...] = ()

    def _sink(self, **config):
        from rasl.devices.sacn.sink import SacnSinkNode

        node = SacnSinkNode(SacnSinkNode.Config(id="out", target_host="127.0.0.1", **config))
        output = self._Output()
        node._sender = {node._target_universe: output}  # stands in for sacn.sACNsender
        return node, output

    def test_it_drives_the_scheduler_at_the_rate_min_interval_allows(self) -> None:
        from rasl.graph import GraphBuilder
        from rasl.runtime.unified import find_rate_drivers

        builder = GraphBuilder()
        builder.add_node(self._sink(min_interval_ms=25)[0])
        assert find_rate_drivers(builder.build()) == {"out": 40.0}

    async def test_pixels_go_out_in_row_order_padded_to_a_universe(self) -> None:
        node, output = self._sink(input_port="pixels")
        assert node.inputs.names == ("pixels",)
        node.inputs.get("pixels")._set_frame(_matrix([[1.0, 0.5, 0.0], [0.2, 2.0, -1.0]]))
        await node.pull(TICK)
        assert len(output.dmx_data) == 512
        assert output.dmx_data[:7] == (255, 127, 0, 51, 255, 0, 0)

    async def test_more_than_a_universe_is_cut_at_512(self) -> None:
        node, output = self._sink()
        node.inputs.get("input")._set_frame(_matrix(np.ones((200, 3))))
        await node.pull(TICK)
        assert output.dmx_data == (255,) * 512

    async def test_nothing_is_sent_before_a_frame_arrives(self) -> None:
        node, output = self._sink()
        await node.pull(TICK)
        assert output.dmx_data == ()
