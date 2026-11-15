"""The sACN sink, pulled as the runtime pulls it."""

from __future__ import annotations

import numpy as np

from rasl.graph.node import TickContext
from rasl.signal import Frame, MatrixPayload

TICK = TickContext(tick=0, t=0.0, dt=0.0, wall_time=0.0)


def _matrix(values) -> Frame:
    return Frame(topic="test", timestamp=0.0, payload=MatrixPayload(np.asarray(values, dtype=np.float32)))


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
        from rasl.runtime import find_rate_drivers

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
