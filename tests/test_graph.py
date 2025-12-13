"""Unit tests for the graph builder and execution plan."""

import warnings

import pytest

from rasl.engine.frames import MatrixPayload, Frame
from rasl.engine.graph import CycleWarning, Edge, ExecutionPlan, GraphBuilder
from rasl.engine.nodes import NodeContext
from rasl.engine.ports import InputPortSpec, OutputPortSpec, PortGroup


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
