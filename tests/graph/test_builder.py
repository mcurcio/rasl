"""Unit tests for the graph builder and execution plan."""

import warnings

import pytest

from rasl.graph import CycleWarning, Edge, ExecutionPlan, GraphBuilder
from rasl.graph.node import NodeContext
from rasl.graph.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.signal import Frame, MatrixPayload


class MockSourceNode:
    """Mock source node for testing."""

    # Source: no inputs, single output
    outputs = PortGroup.outputs(output=OutputPortSpec(MatrixPayload))

    def __init__(self, node_id: str) -> None:
        """Initialize mock source node."""
        self.id = node_id

    async def start(self, ctx: NodeContext) -> None:
        """Start the node."""
        pass

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        """Handle incoming frames."""
        pass

    async def stop(self, ctx: NodeContext) -> None:
        """Stop the node."""
        pass


class MockTransformNode:
    """Mock transform node for testing."""

    inputs = PortGroup.inputs(input=InputPortSpec(MatrixPayload))
    outputs = PortGroup.outputs(output=OutputPortSpec(MatrixPayload))

    def __init__(self, node_id: str) -> None:
        """Initialize mock transform node."""
        self.id = node_id

    async def start(self, ctx: NodeContext) -> None:
        """Start the node."""
        pass

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        """Handle incoming frames."""
        pass

    async def stop(self, ctx: NodeContext) -> None:
        """Stop the node."""
        pass


class MockSinkNode:
    """Mock sink node for testing."""

    inputs = PortGroup.inputs(input=InputPortSpec(MatrixPayload))
    # Sink: no outputs

    def __init__(self, node_id: str) -> None:
        """Initialize mock sink node."""
        self.id = node_id

    async def start(self, ctx: NodeContext) -> None:
        """Start the node."""
        pass

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        """Handle incoming frames."""
        pass

    async def stop(self, ctx: NodeContext) -> None:
        """Stop the node."""
        pass


class TestEdge:
    """Tests for the Edge dataclass."""

    def test_edge_creation(self) -> None:
        """Test edge creation with all fields."""
        edge = Edge(
            source="node1",
            source_port="output",
            target="node2",
            target_port="input",
        )

        assert edge.source == "node1"
        assert edge.source_port == "output"
        assert edge.target == "node2"
        assert edge.target_port == "input"

    def test_edge_is_frozen(self) -> None:
        """Test that edges are immutable."""
        edge = Edge("a", "out", "b", "in")

        with pytest.raises(AttributeError):
            edge.source = "c"  # type: ignore[misc]


class TestGraphBuilder:
    """Tests for the GraphBuilder class."""

    def test_add_node(self) -> None:
        """Test adding a node to the builder."""
        builder = GraphBuilder()
        node = MockSourceNode("source1")

        builder.add_node(node)

        assert "source1" in builder.nodes
        assert builder.nodes["source1"] is node

    def test_add_duplicate_node_raises(self) -> None:
        """Test that adding duplicate node IDs raises ValueError."""
        builder = GraphBuilder()
        node1 = MockSourceNode("source1")
        node2 = MockSourceNode("source1")

        builder.add_node(node1)

        with pytest.raises(ValueError, match="Duplicate node id"):
            builder.add_node(node2)

    def test_connect_nodes(self) -> None:
        """Test connecting two nodes."""
        builder = GraphBuilder()
        source = MockSourceNode("source")
        sink = MockSinkNode("sink")

        builder.add_node(source)
        builder.add_node(sink)
        builder.connect("source", "output", "sink", "input")

        edges = builder.edges
        assert len(edges) == 1
        assert edges[0].source == "source"
        assert edges[0].target == "sink"

    def test_connect_unknown_source_raises(self) -> None:
        """Test that connecting from unknown source raises KeyError."""
        builder = GraphBuilder()
        sink = MockSinkNode("sink")
        builder.add_node(sink)

        with pytest.raises(KeyError, match="Unknown source node"):
            builder.connect("unknown", "output", "sink", "input")

    def test_connect_unknown_target_raises(self) -> None:
        """Test that connecting to unknown target raises KeyError."""
        builder = GraphBuilder()
        source = MockSourceNode("source")
        builder.add_node(source)

        with pytest.raises(KeyError, match="Unknown target node"):
            builder.connect("source", "output", "unknown", "input")

    def test_build_simple_chain(self) -> None:
        """Test building a simple source -> transform -> sink chain."""
        builder = GraphBuilder()
        source = MockSourceNode("source")
        transform = MockTransformNode("transform")
        sink = MockSinkNode("sink")

        builder.add_node(source)
        builder.add_node(transform)
        builder.add_node(sink)
        builder.connect("source", "output", "transform", "input")
        builder.connect("transform", "output", "sink", "input")

        plan = builder.build()

        assert len(plan.nodes) == 3
        assert plan.topological_order == ("source", "transform", "sink")

    def test_build_fan_out(self) -> None:
        """Test building a graph with fan-out (one source, multiple sinks)."""
        builder = GraphBuilder()
        source = MockSourceNode("source")
        sink1 = MockSinkNode("sink1")
        sink2 = MockSinkNode("sink2")

        builder.add_node(source)
        builder.add_node(sink1)
        builder.add_node(sink2)
        builder.connect("source", "output", "sink1", "input")
        builder.connect("source", "output", "sink2", "input")

        plan = builder.build()

        assert len(plan.nodes) == 3
        # Source must come before sinks
        assert plan.topological_order.index("source") < plan.topological_order.index("sink1")
        assert plan.topological_order.index("source") < plan.topological_order.index("sink2")

    def test_build_with_cycle_raises_when_disallowed(self) -> None:
        """Test that building a graph with a cycle raises ValueError when allow_cycles=False."""
        builder = GraphBuilder()
        node1 = MockTransformNode("node1")
        node2 = MockTransformNode("node2")

        builder.add_node(node1)
        builder.add_node(node2)
        builder.connect("node1", "output", "node2", "input")
        builder.connect("node2", "output", "node1", "input")

        with pytest.raises(ValueError, match="Cycle"):
            builder.build(allow_cycles=False)

    def test_build_with_cycle_warns_by_default(self) -> None:
        """Test that building a graph with a cycle emits warning by default."""
        builder = GraphBuilder()
        node1 = MockTransformNode("node1")
        node2 = MockTransformNode("node2")

        builder.add_node(node1)
        builder.add_node(node2)
        builder.connect("node1", "output", "node2", "input")
        builder.connect("node2", "output", "node1", "input")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            plan = builder.build()  # allow_cycles=True by default

            assert len(w) == 1
            assert issubclass(w[0].category, CycleWarning)
            assert "Cycle" in str(w[0].message)

        # Plan is still built successfully
        assert plan is not None
        assert len(plan.nodes) == 2
        assert len(plan.topological_order) == 2

    def test_build_with_self_loop_warns(self) -> None:
        """Test that a self-loop is detected and warned about."""
        builder = GraphBuilder()
        node = MockTransformNode("node")

        builder.add_node(node)
        builder.connect("node", "output", "node", "input")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            plan = builder.build()

            assert len(w) == 1
            assert issubclass(w[0].category, CycleWarning)

        assert plan is not None

    def test_build_adjacency(self) -> None:
        """Test that adjacency map is correctly built."""
        builder = GraphBuilder()
        source = MockSourceNode("source")
        sink = MockSinkNode("sink")

        builder.add_node(source)
        builder.add_node(sink)
        builder.connect("source", "output", "sink", "input")

        plan = builder.build()

        assert len(plan.adjacency["source"]) == 1
        assert plan.adjacency["source"][0].target == "sink"
        assert len(plan.adjacency["sink"]) == 0


class TestExecutionPlan:
    """Tests for the ExecutionPlan dataclass."""

    def test_execution_plan_structure(self) -> None:
        """Test execution plan has correct structure."""
        builder = GraphBuilder()
        source = MockSourceNode("source")
        sink = MockSinkNode("sink")

        builder.add_node(source)
        builder.add_node(sink)
        builder.connect("source", "output", "sink", "input")

        plan = builder.build()

        assert isinstance(plan, ExecutionPlan)
        assert isinstance(plan.nodes, dict)
        assert isinstance(plan.adjacency, dict)
        assert isinstance(plan.topological_order, tuple)


class _Ported:
    """A node with one output and one input port, of the given specs."""

    def __init__(self, node_id: str, *, out: OutputPortSpec | None = None, inp: InputPortSpec | None = None) -> None:
        self.id = node_id
        self.outputs = PortGroup.outputs(out=out or OutputPortSpec(MatrixPayload))
        self.inputs = PortGroup.inputs(**{"in": inp or InputPortSpec(MatrixPayload)})

    async def start(self, ctx: NodeContext) -> None:
        pass

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        pass

    async def stop(self, ctx: NodeContext) -> None:
        pass


class TestConnectValidation:
    """What GraphBuilder.connect refuses (owner, 2026-11-14: slices out of
    range and unknown type names are load errors; 2026-11-16: duplicate edges,
    overlapping destinations and fixed-count mismatches too)."""

    @staticmethod
    def _builder(source: _Ported, target: _Ported) -> GraphBuilder:
        builder = GraphBuilder()
        builder.add_node(source)
        builder.add_node(target)
        return builder

    @pytest.mark.parametrize(
        ("source_slice", "target_slice", "port"),
        [
            ((600, 900), None, "a.out"),  # wholly past the end
            ((500, 520), None, "a.out"),  # ends past the end
            ((512, None), None, "a.out"),  # starts at the end: nothing left
            (None, (2, 4), "b.in"),
            (None, (3, None), "b.in"),
        ],
    )
    def test_a_slice_past_the_end_of_a_fixed_port_is_refused(self, source_slice, target_slice, port) -> None:
        from rasl.graph import Slice

        builder = self._builder(
            _Ported("a", out=OutputPortSpec(MatrixPayload, count=512)),
            _Ported("b", inp=InputPortSpec(MatrixPayload, count=3)),
        )
        with pytest.raises(ValueError, match=rf"out of range for port {port}, which has \d+ elements"):
            builder.connect(
                "a", "out", "b", "in",
                Slice(*source_slice) if source_slice else None,
                Slice(*target_slice) if target_slice else None,
            )
        assert builder.edges == []

    def test_a_slice_past_the_upper_bound_of_a_variable_port_is_refused(self) -> None:
        from rasl.graph import Slice

        builder = self._builder(_Ported("a"), _Ported("b", inp=InputPortSpec(MatrixPayload, count=(1, 10))))
        with pytest.raises(ValueError, match="b.in, which has at most 10 elements"):
            builder.connect("a", "out", "b", "in", None, Slice(8, 12))

    def test_slices_inside_their_ports_connect(self) -> None:
        from rasl.graph import Slice

        builder = self._builder(
            _Ported("a", out=OutputPortSpec(MatrixPayload, count=512)),
            _Ported("b", inp=InputPortSpec(MatrixPayload, count=3)),
        )
        builder.connect("a", "out", "b", "in", Slice(509, 512), Slice(0, 3))
        assert len(builder.edges) == 1

        builder = self._builder(
            _Ported("a", out=OutputPortSpec(MatrixPayload, count=512)),
            _Ported("b", inp=InputPortSpec(MatrixPayload, count=3)),
        )
        builder.connect("a", "out", "b", "in", Slice(511, None), Slice(2, None))
        assert len(builder.edges) == 1

    def test_a_slice_on_an_unbounded_port_cannot_be_checked(self) -> None:
        from rasl.graph import Slice

        builder = self._builder(_Ported("a"), _Ported("b"))
        builder.connect("a", "out", "b", "in", Slice(600, 900), Slice(0, 300))
        assert len(builder.edges) == 1

    def test_an_input_naming_an_unregistered_type_is_refused(self) -> None:
        builder = self._builder(_Ported("a"), _Ported("b", inp=InputPortSpec(("matrix", "colour"))))
        with pytest.raises(TypeError, match=r"Port b\.in names a payload type that is not registered: 'colour'"):
            builder.connect("a", "out", "b", "in")

    def test_an_output_naming_an_unregistered_type_is_refused(self) -> None:
        builder = self._builder(_Ported("a", out=OutputPortSpec("colour")), _Ported("b"))
        with pytest.raises(TypeError, match=r"Port a\.out names a payload type that is not registered: 'colour'"):
            builder.connect("a", "out", "b", "in")

    def test_registered_type_names_connect(self) -> None:
        builder = self._builder(_Ported("a", out=OutputPortSpec("matrix")), _Ported("b", inp=InputPortSpec("matrix")))
        builder.connect("a", "out", "b", "in")
        assert len(builder.edges) == 1


class TestConnectCountsAndOverlaps:
    """Owner, 2026-11-16: duplicate edges, overlapping destinations and a count
    mismatch between fixed ports are load errors."""

    @staticmethod
    def _builder(*nodes: _Ported) -> GraphBuilder:
        builder = GraphBuilder()
        for node in nodes:
            builder.add_node(node)
        return builder

    def test_a_fixed_output_into_a_fixed_input_of_another_count_is_refused(self) -> None:
        builder = self._builder(
            _Ported("a", out=OutputPortSpec(MatrixPayload, count=512)),
            _Ported("b", inp=InputPortSpec(MatrixPayload, count=3)),
        )
        with pytest.raises(ValueError, match=r"Count mismatch: a\.out supplies 512 elements, but b\.in takes 3"):
            builder.connect("a", "out", "b", "in")
        assert builder.edges == []

    def test_slices_of_different_lengths_are_refused(self) -> None:
        from rasl.graph import Slice

        builder = self._builder(_Ported("a"), _Ported("b"))
        with pytest.raises(ValueError, match=r"a\.out\[0~4\] supplies 4 elements, but b\.in\[0~3\] takes 3"):
            builder.connect("a", "out", "b", "in", Slice(0, 4), Slice(0, 3))

    def test_repeat_counts_toward_the_rows_supplied(self) -> None:
        from rasl.graph import Slice

        def nodes() -> GraphBuilder:
            return self._builder(
                _Ported("a", out=OutputPortSpec(MatrixPayload, count=1)),
                _Ported("b", inp=InputPortSpec(MatrixPayload, count=3)),
            )

        builder = nodes()
        builder.connect("a", "out", "b", "in", repeat=3)
        assert len(builder.edges) == 1
        with pytest.raises(ValueError, match=r"a\.out supplies 3 elements \(repeated 3 times\), but b\.in\[1~\] takes 2"):
            nodes().connect("a", "out", "b", "in", None, Slice(1, None), repeat=3)

    def test_a_variable_side_is_not_compared(self) -> None:
        builder = self._builder(_Ported("a"), _Ported("b", inp=InputPortSpec(MatrixPayload, count=3)))
        builder.connect("a", "out", "b", "in")
        assert len(builder.edges) == 1

    def test_the_same_edge_twice_is_refused(self) -> None:
        builder = self._builder(_Ported("a"), _Ported("b"))
        builder.connect("a", "out", "b", "in")
        with pytest.raises(ValueError, match=r"Duplicate connection: a\.out is already connected to b\.in"):
            builder.connect("a", "out", "b", "in")
        assert len(builder.edges) == 1

    def test_two_unsliced_edges_into_one_port_overlap(self) -> None:
        builder = self._builder(_Ported("a"), _Ported("c"), _Ported("b"))
        builder.connect("a", "out", "b", "in")
        with pytest.raises(
            ValueError,
            match=r"Overlapping connections into b\.in: c\.out writes rows \[0~\], which a\.out already writes \(rows \[0~\]\)",
        ):
            builder.connect("c", "out", "b", "in")

    def test_overlapping_target_slices_are_refused(self) -> None:
        from rasl.graph import Slice

        builder = self._builder(_Ported("a"), _Ported("c"), _Ported("b"))
        builder.connect("a", "out", "b", "in", None, Slice(0, 50))
        with pytest.raises(ValueError, match=r"c\.out writes rows \[40~\], which a\.out already writes \(rows \[0~50\]\)"):
            builder.connect("c", "out", "b", "in", None, Slice(40, None))

    def test_adjacent_target_slices_connect(self) -> None:
        from rasl.graph import Slice

        builder = self._builder(_Ported("a"), _Ported("c"), _Ported("b"))
        builder.connect("a", "out", "b", "in", None, Slice(0, 50))
        builder.connect("c", "out", "b", "in", None, Slice(50, None))
        assert len(builder.edges) == 2

    def test_an_unsliced_fixed_source_ends_where_its_rows_end(self) -> None:
        from rasl.graph import Slice

        builder = self._builder(
            _Ported("a", out=OutputPortSpec(MatrixPayload, count=10)), _Ported("c"), _Ported("b")
        )
        builder.connect("a", "out", "b", "in")
        builder.connect("c", "out", "b", "in", None, Slice(10, None))
        assert len(builder.edges) == 2

    def test_repeat_until_ends_the_rows_written(self) -> None:
        from rasl.graph import Slice

        builder = self._builder(_Ported("a"), _Ported("c"), _Ported("b"))
        builder.connect("a", "out", "b", "in", repeat_until=30)
        with pytest.raises(ValueError, match=r"rows \[29~\], which a\.out already writes \(rows \[0~30\]\)"):
            builder.connect("c", "out", "b", "in", None, Slice(29, None))
        builder.connect("c", "out", "b", "in", None, Slice(30, None))
        assert len(builder.edges) == 2


class TestConnectErrorsNameTheirPorts:
    """Every connect error is a ConnectError with both ends (owner, 2026-11-16: errors
    carry the connect ports), and still the built-in exception it was."""

    def test_a_count_mismatch_carries_both_ends_and_both_counts(self) -> None:
        from rasl.graph import ConnectError, ConnectProblem, Endpoint

        builder = GraphBuilder()
        builder.add_node(_Ported("a", out=OutputPortSpec(MatrixPayload, count=512)))
        builder.add_node(_Ported("b", inp=InputPortSpec(MatrixPayload, count=3)))
        with pytest.raises(ValueError) as caught:
            builder.connect("a", "out", "b", "in")
        error = caught.value
        assert isinstance(error, ConnectError)
        assert error.problem is ConnectProblem.COUNT
        assert (error.source, error.target) == (Endpoint("a", "out"), Endpoint("b", "in"))
        assert (error.supplied, error.takes) == (512, 3)

    def test_an_unknown_node_is_a_key_error_that_prints_plainly(self) -> None:
        from rasl.graph import ConnectError, ConnectProblem

        builder = GraphBuilder()
        builder.add_node(_Ported("b"))
        with pytest.raises(KeyError) as caught:
            builder.connect("a", "out", "b", "in")
        assert isinstance(caught.value, ConnectError)
        assert caught.value.problem is ConnectProblem.UNKNOWN_NODE
        assert str(caught.value) == "Unknown source node 'a'"


class TestMatrixIntoColor:
    """Owner, 2026-11-16: a more general type feeds a port of a more specific type of its
    inheritance chain, retyped (a matrix into a color or a bool port); a component
    mismatch is refused at load when the width is known, or fails on the first frame."""

    @staticmethod
    def _builder(out: OutputPortSpec, inp: InputPortSpec) -> GraphBuilder:
        builder = GraphBuilder()
        builder.add_node(_Ported("a", out=out))
        builder.add_node(_Ported("b", inp=inp))
        return builder

    def test_a_matrix_of_the_colors_width_connects(self) -> None:
        from rasl.color.payloads import HsbkColorPayload

        builder = self._builder(OutputPortSpec(MatrixPayload, components=4), InputPortSpec(HsbkColorPayload))
        builder.connect("a", "out", "b", "in")
        assert len(builder.edges) == 1

    def test_a_known_width_that_differs_is_refused_at_load(self) -> None:
        from rasl.color.payloads import HsbkColorPayload
        from rasl.graph import ConnectProblem, ConnectTypeError

        builder = self._builder(OutputPortSpec(MatrixPayload, components=1), InputPortSpec(HsbkColorPayload))
        with pytest.raises(ConnectTypeError, match=r"a\.out emits 1 columns, but b\.in takes HsbkColorPayload \(4 components\)") as caught:
            builder.connect("a", "out", "b", "in")
        assert caught.value.problem is ConnectProblem.COMPONENTS
        assert (caught.value.supplied, caught.value.takes) == (1, 4)

    def test_another_color_type_still_needs_a_color_node(self) -> None:
        from rasl.color.payloads import HsbkColorPayload, RgbColorPayload
        from rasl.graph import ConnectProblem, ConnectTypeError

        builder = self._builder(OutputPortSpec(RgbColorPayload), InputPortSpec(HsbkColorPayload))
        with pytest.raises(ConnectTypeError) as caught:
            builder.connect("a", "out", "b", "in")
        assert caught.value.problem is ConnectProblem.TYPE

    def test_an_unknown_width_is_checked_on_the_first_frame(self) -> None:
        import numpy as np

        from rasl.color.payloads import HsbkColorPayload
        from rasl.graph import CoercionError
        from rasl.signal import Frame

        builder = self._builder(OutputPortSpec(MatrixPayload), InputPortSpec(HsbkColorPayload))
        builder.connect("a", "out", "b", "in")
        program = builder.build().input_programs[("b", "in")]

        def frames(columns: int):
            frame = Frame(topic="t", timestamp=0.0, payload=MatrixPayload(np.zeros((2, columns), dtype=np.float32)))
            return lambda *_: frame

        delivered = program.populate(0, frames(4), lambda *_: np.zeros((2, 4), dtype=np.float32))
        assert isinstance(delivered.payload, HsbkColorPayload)
        with pytest.raises(CoercionError, match=r"a\.out into b\.in: MatrixPayload of 1 columns cannot be made a HsbkColorPayload \(4 components\)") as caught:
            program.populate(0, frames(1), lambda *_: np.zeros((2, 4), dtype=np.float32))
        assert (caught.value.supplied, caught.value.takes) == (1, 4)

    def test_a_generic_color_of_another_model_fails_on_its_first_frame(self) -> None:
        import numpy as np

        from rasl.color import ColorPayload
        from rasl.color.payloads import RgbColorPayload
        from rasl.graph import CoercionError
        from rasl.signal import Frame

        builder = self._builder(OutputPortSpec(ColorPayload), InputPortSpec(RgbColorPayload))
        builder.connect("a", "out", "b", "in")
        program = builder.build().input_programs[("b", "in")]

        def frames(model: str):
            frame = Frame(topic="t", timestamp=0.0, payload=ColorPayload(np.zeros((2, 3), dtype=np.float32), model))
            return lambda *_: frame

        assert isinstance(program.populate(0, frames("srgb"), None).payload, RgbColorPayload)
        with pytest.raises(CoercionError, match="model hsl cannot be made a RgbColorPayload"):
            program.populate(0, frames("hsl"), None)

    def test_a_matrix_feeds_a_bool_port_as_a_mask(self) -> None:
        import numpy as np

        from rasl.signal import BoolPayload, Frame

        builder = self._builder(OutputPortSpec(MatrixPayload), InputPortSpec(BoolPayload))
        builder.connect("a", "out", "b", "in")
        program = builder.build().input_programs[("b", "in")]
        frame = Frame(topic="t", timestamp=0.0, payload=MatrixPayload(np.array([[0.0], [0.4]], dtype=np.float32)))
        delivered = program.populate(0, lambda *_: frame, None)
        assert isinstance(delivered.payload, BoolPayload)
        assert delivered.payload.data.tolist() == [[0.0], [1.0]]


class TestPlanWiring:
    """ExecutionPlan.wiring: which of a node's ports have edges."""

    def test_wiring_lists_connected_inputs_and_outputs(self) -> None:
        from rasl.graph import GraphBuilder
        from rasl.graph.node import BaseNode, TickContext, Wiring
        from rasl.graph.ports import InputPortSpec, OutputPortSpec, PortGroup
        from rasl.signal import MatrixPayload

        class _Node(BaseNode):
            def __init__(self, node_id: str) -> None:
                self.id = node_id
                self.inputs = PortGroup.inputs(a=InputPortSpec(MatrixPayload), b=InputPortSpec(MatrixPayload))
                self.outputs = PortGroup.outputs(x=OutputPortSpec(MatrixPayload), y=OutputPortSpec(MatrixPayload))

            async def pull(self, tick: TickContext) -> None:
                """Do nothing."""

        builder = GraphBuilder()
        for node_id in ("one", "two"):
            builder.add_node(_Node(node_id))
        builder.connect("one", "x", "two", "a")
        plan = builder.build()
        assert plan.wiring("one") == Wiring(outputs=frozenset({"x"}))
        assert plan.wiring("two") == Wiring(inputs=frozenset({"a"}))
