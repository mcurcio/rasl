"""The compiled routing of input ports: the copy and repeat ops, and the program that
builds an input port's frame each pull (rasl-pd0.15)."""

from __future__ import annotations

import numpy as np
import pytest

from rasl.color import RgbColorPayload
from rasl.graph import CycleWarning, GraphBuilder, Slice
from rasl.graph.node import NodeContext
from rasl.graph.ports import FrameBuffers, InputPortSpec, OutputPortSpec, PortGroup
from rasl.graph.routing import CopySliceOp, InputPortProgram, RepeatSliceOp
from rasl.signal import Frame, MatrixPayload


def _rows(n: int, cols: int = 1, start: float = 0.0) -> np.ndarray:
    """``n`` rows of ``cols`` columns; row i holds ``start + i`` in every column."""
    return np.repeat((np.arange(n, dtype=np.float32) + start).reshape(-1, 1), cols, axis=1)


def _copy(src_start=0, src_end=-1, dst_start=0, dst_end=-1) -> CopySliceOp:
    return CopySliceOp("a", "out", False, src_start, src_end, dst_start, dst_end)


def _repeat(src_start=0, src_end=-1, dst_start=0, dst_end=-1, repeat=1, repeat_until=None) -> RepeatSliceOp:
    return RepeatSliceOp("a", "out", False, src_start, src_end, dst_start, dst_end, repeat, repeat_until)


class TestCopySliceOp:
    def test_a_slice_lands_at_its_destination_and_nothing_else_is_written(self) -> None:
        dst = np.full((6, 1), -1.0, dtype=np.float32)
        _copy(src_start=2, src_end=5, dst_start=1).populate(dst, _rows(8))
        assert dst.ravel().tolist() == [-1, 2, 3, 4, -1, -1]

    def test_an_open_slice_runs_to_the_source_end_and_stops_at_the_destination_end(self) -> None:
        dst = np.full((4, 1), -1.0, dtype=np.float32)
        _copy(src_start=5, dst_start=2).populate(dst, _rows(10))
        assert dst.ravel().tolist() == [-1, -1, 5, 6]

    def test_rows_are_elements_so_every_component_moves_together(self) -> None:
        dst = np.zeros((2, 3), dtype=np.float32)
        _copy(src_start=1, src_end=3).populate(dst, _rows(4, cols=3))
        assert dst.tolist() == [[1, 1, 1], [2, 2, 2]]

    def test_required_rows_follows_the_destination_end_or_the_source_slice(self) -> None:
        assert _copy(dst_end=7).required_rows(100) == 7
        assert _copy(src_start=2, src_end=5, dst_start=10).required_rows(100) == 13
        assert _copy(src_start=4, dst_start=1).required_rows(10) == 7


class TestRepeatSliceOp:
    """rasl-pd0.11: a repeat on a sliced connection keeps the slice's start and length."""

    def test_a_sliced_fixed_source_repeats_the_slice_not_the_whole_output(self) -> None:
        dst = np.full((14, 1), -1.0, dtype=np.float32)
        op = _repeat(src_start=4, repeat=2)
        assert op.required_rows(10) == 12
        op.populate(dst, _rows(10))
        assert dst.ravel().tolist() == [4, 5, 6, 7, 8, 9, 4, 5, 6, 7, 8, 9, -1, -1]

    def test_a_sliced_variable_source_repeats_what_arrived(self) -> None:
        dst = np.full((12, 1), -1.0, dtype=np.float32)
        _repeat(src_start=4, repeat=3).populate(dst, _rows(7))
        assert dst.ravel().tolist() == [4, 5, 6, 4, 5, 6, 4, 5, 6, -1, -1, -1]

    def test_repeat_until_fills_that_many_rows_and_cuts_the_last_copy_short(self) -> None:
        dst = np.full((8, 1), -1.0, dtype=np.float32)
        op = _repeat(src_start=0, src_end=3, dst_start=1, repeat_until=5)
        assert op.required_rows(10) == 6
        op.populate(dst, _rows(10))
        assert dst.ravel().tolist() == [-1, 0, 1, 2, 0, 1, -1, -1]

    def test_copies_stop_at_the_destination_end(self) -> None:
        dst = np.full((5, 1), -1.0, dtype=np.float32)
        _repeat(src_start=0, src_end=2, dst_end=3, repeat=4).populate(dst, _rows(2, start=7))
        assert dst.ravel().tolist() == [7, 8, 7, -1, -1]


class _Node:
    """A node with ``out`` and ``in`` ports of the given specs."""

    def __init__(
        self,
        node_id: str,
        *,
        out: OutputPortSpec | None = None,
        inp: InputPortSpec | None = None,
        count: int | None = None,
    ) -> None:
        self.id = node_id
        self.outputs = PortGroup.outputs(out=out or OutputPortSpec(MatrixPayload, count=count))
        self.inputs = PortGroup.inputs(**{"in": inp or InputPortSpec(MatrixPayload)})

    async def start(self, ctx: NodeContext) -> None:
        pass

    async def stop(self, ctx: NodeContext) -> None:
        pass


def _frame(data: np.ndarray, *, topic: str = "t", payload_type=MatrixPayload) -> Frame:
    return Frame(topic=topic, timestamp=1.5, payload=payload_type(data), metadata={"from": topic})


class _Run:
    """Runs one input port's compiled program the way the executor does, with frames
    supplied by the test instead of upstream pulls."""

    def __init__(self, program: InputPortProgram) -> None:
        self.program = program
        if program.passthrough is None:
            program.target._buffers = FrameBuffers()  # what the runtime's bind_ports gives it
        self.reads: list[tuple[str, str, bool]] = []

    def __call__(self, frames: dict[str, Frame | None]) -> Frame | None:
        def resolve(node: str, port: str, is_back_edge: bool, tick: int) -> Frame | None:
            self.reads.append((node, port, is_back_edge))
            return frames.get(node)

        published = self.program.populate(tick=0, resolve=resolve)
        assert self.program.target.read() is published
        return published


def _program(nodes, connections, target: str = "b") -> _Run:
    builder = GraphBuilder()
    for node in nodes:
        builder.add_node(node)
    for args, kwargs in connections:
        builder.connect(*args, **kwargs)
    return _Run(builder.build().input_programs[(target, "in")])


class TestInputPortProgram:
    def test_one_whole_connection_hands_over_the_upstream_frame_itself(self) -> None:
        run = _program([_Node("a", count=3), _Node("b")], [(("a", "out", "b", "in"), {})])
        assert run.program.passthrough == ("a", "out") and run.program.ops == ()
        sent = _frame(_rows(3))
        assert run({"a": sent}) is sent

    def test_no_upstream_frame_builds_no_frame(self) -> None:
        run = _program([_Node("a", count=2), _Node("b")], [(("a", "out", "b", "in", Slice(0, 2)), {})])
        assert run({}) is None

    def test_sliced_connections_are_assembled_in_one_frame(self) -> None:
        run = _program(
            [_Node("a", count=5), _Node("c", count=2), _Node("b")],
            [
                (("a", "out", "b", "in", Slice(1, 3), Slice(0, 2)), {}),
                (("c", "out", "b", "in", None, Slice(4, None)), {}),
            ],
        )
        built = run({"a": _frame(_rows(5), topic="a"), "c": _frame(_rows(2, start=10), topic="c")})
        assert np.asarray(built.payload).ravel().tolist() == [1, 2, 0, 0, 10, 11]
        # The first source with a frame names the built frame
        assert (built.topic, built.timestamp, dict(built.metadata)) == ("a", 1.5, {"from": "a"})

    def test_rows_no_connection_wrote_this_pull_are_zero_not_last_pulls(self) -> None:
        fixed = InputPortSpec(MatrixPayload, count=4)
        run = _program(
            [_Node("a", count=2), _Node("c", count=2), _Node("b", inp=fixed)],
            [
                (("a", "out", "b", "in", None, Slice(0, 2)), {}),
                (("c", "out", "b", "in", None, Slice(2, 4)), {}),
            ],
        )
        run({"a": _frame(_rows(2, start=1)), "c": _frame(_rows(2, start=5))})
        built = run({"a": _frame(_rows(2, start=1))})
        assert np.asarray(built.payload).ravel().tolist() == [1, 2, 0, 0]

    def test_a_ports_length_is_fixed_and_a_silent_source_leaves_zeros(self) -> None:
        # rasl-00l / rasl-vs5: the length comes from the plan, not from who wrote
        run = _program(
            [_Node("a", count=2), _Node("c", count=2), _Node("b")],
            [
                (("a", "out", "b", "in", None, Slice(0, 2)), {}),
                (("c", "out", "b", "in", None, Slice(2, 4)), {}),
            ],
        )
        assert run.program.fixed_rows == 4
        assert np.asarray(run({"a": _frame(_rows(2, start=1))}).payload).ravel().tolist() == [1, 2, 0, 0]

    def test_a_sliced_repeat_through_the_builder_keeps_the_slice(self) -> None:
        run = _program(
            [_Node("a", out=OutputPortSpec(MatrixPayload, count=10)), _Node("b")],
            [(("a", "out", "b", "in", Slice(4, None)), {"repeat": 2})],
        )
        built = run({"a": _frame(_rows(10))})
        assert np.asarray(built.payload).ravel().tolist() == [4, 5, 6, 7, 8, 9] * 2

    def test_a_built_frame_has_the_type_the_port_takes(self) -> None:
        rgb = InputPortSpec(RgbColorPayload)
        run = _program(
            [_Node("a", out=OutputPortSpec(RgbColorPayload, count=3)), _Node("b", inp=rgb)],
            [(("a", "out", "b", "in", Slice(0, 2)), {"repeat": 2})],
        )
        built = run({"a": _frame(_rows(3, cols=3), payload_type=RgbColorPayload)})
        assert type(built.payload) is RgbColorPayload
        assert np.asarray(built.payload).shape == (4, 3)

    def test_a_back_edge_is_read_as_one(self) -> None:
        builder = GraphBuilder()
        for node in (_Node("a", count=2), _Node("b", count=2)):
            builder.add_node(node)
        builder.connect("a", "out", "b", "in", None, Slice(0, 2))
        builder.connect("b", "out", "a", "in", None, Slice(0, 2))
        with pytest.warns(CycleWarning):
            plan = builder.build()
        flags = {
            key: [op.is_back_edge for op in program.ops] for key, program in plan.input_programs.items()
        }
        assert sorted(flags.values()) == [[False], [True]]

    def test_a_built_frame_is_unchanged_by_the_next_pull_and_reused_at_the_one_after(self) -> None:
        run = _program([_Node("a", count=2), _Node("b")], [(("a", "out", "b", "in", Slice(0, 2)), {})])
        first = run({"a": _frame(_rows(2, start=1))})
        second = run({"a": _frame(_rows(2, start=7))})
        assert np.asarray(first.payload).ravel().tolist() == [1, 2]
        third = run({"a": _frame(_rows(2, start=3))})
        assert np.shares_memory(np.asarray(first.payload), np.asarray(third.payload))
        assert not np.shares_memory(np.asarray(second.payload), np.asarray(third.payload))

    def test_a_source_that_fails_its_type_check_publishes_nothing(self) -> None:
        from rasl.graph import CoercionError

        rgb = InputPortSpec(RgbColorPayload)
        run = _program(
            [_Node("a", out=OutputPortSpec(RgbColorPayload, count=2)), _Node("b", inp=rgb)],
            [(("a", "out", "b", "in", Slice(0, 2)), {})],
        )
        good = run({"a": _frame(_rows(2, cols=3), payload_type=RgbColorPayload)})
        bad = Frame(topic="t", timestamp=0.0, payload=MatrixPayload(_rows(2, cols=2)))
        with pytest.raises(CoercionError):
            run.program.populate(tick=1, resolve=lambda *_: bad)
        assert run.program.target.read() is good
