"""Reshape: regroups a matrix's values row-major into rows of ``components``."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import Field

from rasl.config.build import parse_config
from rasl.config.document import ConfigError
from rasl.graph import ConnectProblem
from rasl.graph.node import BaseNode, SourceNodeConfig, TickContext, get_inputs, get_outputs, node
from rasl.graph.ports import OutputPortSpec, PortGroup
from rasl.nodes.effects.reshape import ReshapeNode
from rasl.signal import Frame, MatrixPayload


class _FixedRowsConfig(SourceNodeConfig):
    """Rows and columns of the matrix the source declares."""

    rows: int | None = Field(None, ge=1)
    columns: int = Field(1, ge=1)


@node("TestFixedRowsSource")
class _FixedRowsSource(BaseNode):
    """Declares an output of ``rows`` (None: unknown) rows of ``columns``; never runs."""

    Config = _FixedRowsConfig

    def __init__(self, config: _FixedRowsConfig) -> None:
        super().__init__(config)
        self.outputs = PortGroup.outputs(
            out=OutputPortSpec(MatrixPayload, count=config.rows, components=config.columns)
        )

    async def pull(self, tick: TickContext) -> None:
        """Do nothing."""


def _tick() -> TickContext:
    return TickContext(tick=0, t=0.0, dt=0.0, wall_time=0.0)


async def _pull(node: ReshapeNode, data: np.ndarray) -> Frame | None:
    node.inputs.input._set_frame(Frame(topic="t", timestamp=0.0, payload=MatrixPayload(data)))
    await node.pull(_tick())
    return node.outputs.output._consume()


def test_the_ports_follow_components() -> None:
    node = ReshapeNode(ReshapeNode.Config(id="r", components=3))
    assert get_inputs(node).get("input").spec.values_multiple_of == 3
    assert get_outputs(node).get("output").spec.known_components == 3


async def test_six_values_into_three_components_are_two_rows() -> None:
    node = ReshapeNode(ReshapeNode.Config(id="r", components=3))
    data = np.arange(6, dtype=np.float32).reshape(6, 1)
    out = await _pull(node, data)
    assert out is not None
    assert out.payload.data.tolist() == [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]]
    data[0, 0] = 99.0
    assert out.payload.data[0, 0] == 0.0  # a new array, not the input's


async def test_rows_are_read_row_major() -> None:
    node = ReshapeNode(ReshapeNode.Config(id="r", components=1))
    out = await _pull(node, np.array([[1, 2, 3], [4, 5, 6]], dtype=np.float32))
    assert out is not None
    assert out.payload.data.reshape(-1).tolist() == [1, 2, 3, 4, 5, 6]


async def test_seven_values_fail_at_pull() -> None:
    node = ReshapeNode(ReshapeNode.Config(id="r", components=3))
    with pytest.raises(ValueError, match="7 values is not a multiple of 3"):
        await _pull(node, np.zeros((7, 1), dtype=np.float32))


async def test_no_frame_writes_nothing() -> None:
    node = ReshapeNode(ReshapeNode.Config(id="r", components=3))
    await node.pull(_tick())
    assert node.outputs.output._consume() is None


def _graph(*lines: str) -> str:
    return "graph {\n" + "\n".join(f"    {line}" for line in lines) + "\n}\n"


class TestAtLoad:
    def test_512_channels_into_reshape_3_is_a_located_multiple_error(self) -> None:
        config = _graph(
            "node TestFixedRowsSource dmx { rows 512; }",
            "node Reshape rgb {",
            "    components 3;",
            "    connect dmx;",
            "}",
        )
        with pytest.raises(ConfigError, match=r"rasl/connect: Node 'rgb': .*512 values") as caught:
            parse_config(config)
        assert caught.value.line == 5
        connection = caught.value.connection
        assert connection is not None
        assert connection.problem is ConnectProblem.MULTIPLE
        assert (connection.supplied, connection.takes) == (512, 3)

    def test_510_channels_load(self) -> None:
        parse_config(_graph(
            "node TestFixedRowsSource dmx { rows 510; }",
            "node Reshape rgb { components 3; connect dmx; }",
        ))

    def test_fan_in_of_432_and_24_loads(self) -> None:
        parse_config(_graph(
            "node TestFixedRowsSource a { rows 432; }",
            "node TestFixedRowsSource b { rows 24; }",
            "node Reshape rgb {",
            "    components 3;",
            "    connect a input[0~432];",
            "    connect b input[432~456];",
            "}",
        ))

    def test_an_unknown_count_loads(self) -> None:
        parse_config(_graph(
            "node TestFixedRowsSource dmx;",
            "node Reshape rgb { components 3; connect dmx; }",
        ))

    def test_components_0_is_a_located_config_error(self) -> None:
        with pytest.raises(ConfigError, match="components: Input should be greater than or equal to 1") as caught:
            parse_config(_graph("node Reshape rgb {", "    components 0;", "}"))
        assert caught.value.line == 3
