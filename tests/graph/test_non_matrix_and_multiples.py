"""What GraphBuilder refuses for a non-matrix payload (owner Q13: no slice, repeat or
fan-in at load) and for a port declaring ``values_multiple_of`` (owner Q18: the padded
buffer counts)."""

from __future__ import annotations

import numpy as np
import pytest

from rasl.graph import (
    ConnectProblem,
    ConnectTypeError,
    GraphBuilder,
    PortTypeError,
    PortValuesError,
    Slice,
)
from rasl.graph.node import NodeContext
from rasl.graph.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.signal import Frame, MatrixPayload, RollingCounter


class _Ported:
    """A node with one output ``out`` and one input ``in``, of the given specs."""

    def __init__(self, node_id: str, *, out: OutputPortSpec | None = None, inp: InputPortSpec | None = None) -> None:
        self.id = node_id
        self.outputs = PortGroup.outputs(out=out or OutputPortSpec(MatrixPayload))
        self.inputs = PortGroup.inputs(**{"in": inp or InputPortSpec(MatrixPayload)})

    async def start(self, ctx: NodeContext) -> None:
        pass

    async def stop(self, ctx: NodeContext) -> None:
        pass


def _builder(*nodes: _Ported) -> GraphBuilder:
    builder = GraphBuilder()
    for node in nodes:
        builder.add_node(node)
    return builder


COUNTER_OUT = OutputPortSpec(RollingCounter)
EITHER_IN = InputPortSpec((MatrixPayload, RollingCounter))


class TestCounterTypes:
    def test_a_counter_into_a_matrix_port_is_a_type_error(self) -> None:
        builder = _builder(_Ported("a", out=COUNTER_OUT), _Ported("b"))
        with pytest.raises(ConnectTypeError) as caught:
            builder.connect("a", "out", "b", "in")
        assert caught.value.problem is ConnectProblem.TYPE

    def test_a_matrix_into_a_counter_port_is_a_type_error(self) -> None:
        builder = _builder(_Ported("a"), _Ported("b", inp=InputPortSpec(RollingCounter)))
        with pytest.raises(ConnectTypeError) as caught:
            builder.connect("a", "out", "b", "in")
        assert caught.value.problem is ConnectProblem.TYPE

    def test_a_counter_passes_through_one_unsliced_edge_untouched(self) -> None:
        builder = _builder(_Ported("a", out=COUNTER_OUT), _Ported("b", inp=InputPortSpec("counter")))
        builder.connect("a", "out", "b", "in")
        program = builder.build().input_programs[("b", "in")]
        frame = Frame(topic="t", timestamp=0.0, payload=RollingCounter(41))
        assert program.populate(0, lambda *_: frame, None) is frame


class TestNotSliceable:
    @pytest.mark.parametrize(
        ("source_slice", "target_slice", "repeat", "repeat_until"),
        [
            (Slice(0, 1), None, 1, None),
            (None, Slice(0, 1), 1, None),
            (None, None, 2, None),
            (None, None, 1, 4),
        ],
    )
    def test_a_slice_or_repeat_of_a_counter_is_refused(self, source_slice, target_slice, repeat, repeat_until) -> None:
        builder = _builder(_Ported("a", out=COUNTER_OUT), _Ported("b", inp=EITHER_IN))
        with pytest.raises(ConnectTypeError, match=r"Not sliceable: a\.out.* emits RollingCounter") as caught:
            builder.connect("a", "out", "b", "in", source_slice, target_slice, repeat, repeat_until)
        assert caught.value.problem is ConnectProblem.NOT_SLICEABLE
        assert builder.edges == []

    def test_a_second_edge_after_a_counter_is_refused(self) -> None:
        builder = _builder(
            _Ported("a", out=COUNTER_OUT),
            _Ported("m", out=OutputPortSpec(MatrixPayload, count=1)),
            _Ported("b", inp=EITHER_IN),
        )
        builder.connect("a", "out", "b", "in")
        with pytest.raises(ConnectTypeError, match=r"a\.out emits RollingCounter, .* cannot share b\.in") as caught:
            builder.connect("m", "out", "b", "in", None, Slice(5, 6))
        assert caught.value.problem is ConnectProblem.NOT_SLICEABLE
        assert caught.value.source.node == "m"

    def test_a_counter_after_a_matrix_is_refused(self) -> None:
        builder = _builder(
            _Ported("m", out=OutputPortSpec(MatrixPayload, count=1)),
            _Ported("a", out=COUNTER_OUT),
            _Ported("b", inp=EITHER_IN),
        )
        builder.connect("m", "out", "b", "in", None, Slice(5, 6))
        with pytest.raises(ConnectTypeError) as caught:
            builder.connect("a", "out", "b", "in")
        assert caught.value.problem is ConnectProblem.NOT_SLICEABLE

    def test_a_pass_through_carrying_a_counter_is_refused_at_build(self) -> None:
        relay = _Ported("r", out=OutputPortSpec(MatrixPayload, same_as="in"), inp=EITHER_IN)
        builder = _builder(_Ported("a", out=COUNTER_OUT), relay, _Ported("b", inp=EITHER_IN))
        builder.connect("a", "out", "r", "in")
        builder.connect("r", "out", "b", "in", Slice(0, 1))
        with pytest.raises(PortTypeError) as caught:
            builder.build()
        assert caught.value.problem is ConnectProblem.NOT_SLICEABLE
        assert caught.value.edge.source == "r"

    def test_slicing_matrices_is_unchanged(self) -> None:
        builder = _builder(_Ported("a"), _Ported("m"), _Ported("b"))
        builder.connect("a", "out", "b", "in", None, Slice(0, 3))
        builder.connect("m", "out", "b", "in", None, Slice(3, 6), 1)
        builder.build()


class TestValuesMultipleOf:
    @staticmethod
    def _into(k: int, *sources: tuple[OutputPortSpec, Slice | None]) -> GraphBuilder:
        nodes = [_Ported(f"s{i}", out=spec) for i, (spec, _) in enumerate(sources)]
        builder = _builder(*nodes, _Ported("t", inp=InputPortSpec(MatrixPayload, values_multiple_of=k)))
        for i, (_, target_slice) in enumerate(sources):
            builder.connect(f"s{i}", "out", "t", "in", None, target_slice)
        return builder

    def test_values_multiple_of_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="values_multiple_of"):
            InputPortSpec(MatrixPayload, values_multiple_of=0)

    def test_a_single_edge_counts_rows_times_width(self) -> None:
        builder = self._into(3, (OutputPortSpec(MatrixPayload, count=512, components=1), None))
        with pytest.raises(PortValuesError, match=r"t\.in is supplied 512 values .* not a multiple of 3") as caught:
            builder.build()
        error = caught.value
        assert isinstance(error, PortTypeError)
        assert error.problem is ConnectProblem.MULTIPLE
        assert (error.supplied, error.takes) == (512, 3)
        assert (error.edge.source, error.edge.target) == ("s0", "t")

    def test_a_width_counts_toward_the_total(self) -> None:
        self._into(6, (OutputPortSpec(MatrixPayload, count=170, components=3), None)).build()
        with pytest.raises(PortValuesError):
            self._into(4, (OutputPortSpec(MatrixPayload, count=170, components=3), None)).build()

    def test_fan_in_counts_the_padded_buffer(self) -> None:
        # 2 rows of width 1 and 2 rows of width 3 into a buffer of 4 rows x 3 columns: 12
        builder = self._into(
            4,
            (OutputPortSpec(MatrixPayload, count=2, components=1), Slice(0, 2)),
            (OutputPortSpec(MatrixPayload, count=2, components=3), Slice(2, 4)),
        )
        builder.build()
        builder = self._into(
            8,
            (OutputPortSpec(MatrixPayload, count=2, components=1), Slice(0, 2)),
            (OutputPortSpec(MatrixPayload, count=2, components=3), Slice(2, 4)),
        )
        with pytest.raises(PortValuesError) as caught:
            builder.build()
        assert caught.value.supplied == 12
        assert caught.value.edge.source == "s0"

    def test_a_gap_before_the_slice_is_padding_that_counts(self) -> None:
        # rows 1..3 written: the buffer has 3 rows
        self._into(3, (OutputPortSpec(MatrixPayload, count=2, components=1), Slice(1, 3))).build()
        with pytest.raises(PortValuesError):
            self._into(2, (OutputPortSpec(MatrixPayload, count=2, components=1), Slice(1, 3))).build()

    def test_the_load_total_matches_the_runtime_buffer(self) -> None:
        builder = self._into(
            1,
            (OutputPortSpec(MatrixPayload, count=2, components=1), Slice(0, 2)),
            (OutputPortSpec(MatrixPayload, count=2, components=3), Slice(3, 5)),
        )
        expected = builder._supplied_values(
            InputPortSpec(MatrixPayload), builder.edges
        )
        program = builder.build().input_programs[("t", "in")]
        frames = {
            "s0": Frame(topic="t", timestamp=0.0, payload=MatrixPayload(np.ones((2, 1), dtype=np.float32))),
            "s1": Frame(topic="t", timestamp=0.0, payload=MatrixPayload(np.ones((2, 3), dtype=np.float32))),
        }
        delivered = program.populate(
            0,
            lambda node, *_: frames[node],
            lambda key, rows, cols: np.zeros((rows, cols), dtype=np.float32),
        )
        assert delivered.payload.data.size == expected == 15

    @pytest.mark.parametrize(
        "spec",
        [OutputPortSpec(MatrixPayload, components=1), OutputPortSpec(MatrixPayload, count=512)],
    )
    def test_an_unknown_count_or_width_is_left_to_the_node(self, spec: OutputPortSpec) -> None:
        self._into(3, (spec, None)).build()
