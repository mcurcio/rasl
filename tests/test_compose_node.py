"""Tests for ComposeNode."""

import numpy as np
import pytest

from rasl.config.directive import Directive
from rasl.config.loader import _extract_config_dict
from rasl.engine.frame import ArrayPayload, Frame
from rasl.engine.graph import Edge, GraphBuilder
from rasl.engine.ports import PortSpec
from rasl.nodes.compose_node import ComposeNode


class TestComposeNodeConfig:
    """Tests for ComposeNode configuration parsing."""

    def test_config_with_ports_dict(self) -> None:
        """Config accepts ports as dict (from nested block)."""
        config = ComposeNode.Config(
            id="test",
            ports={"hue": True, "saturation": True, "lightness": True},
        )
        assert config.ports == ["hue", "saturation", "lightness"]

    def test_config_with_ports_list(self) -> None:
        """Config accepts ports as list."""
        config = ComposeNode.Config(
            id="test",
            ports=["hue", "saturation", "lightness"],
        )
        assert config.ports == ["hue", "saturation", "lightness"]

    def test_config_fill_from_list_of_lists(self) -> None:
        """Config parses fill from list-of-lists (multiple directives)."""
        config = ComposeNode.Config(
            id="test",
            ports=["hue", "saturation", "lightness"],
            fill=[["saturation", 1.0], ["lightness", 0.5]],
        )
        assert config.fill == {"saturation": 1.0, "lightness": 0.5}

    def test_config_fill_from_single_list(self) -> None:
        """Config parses fill from single list (one directive)."""
        config = ComposeNode.Config(
            id="test",
            ports=["hue", "saturation"],
            fill=["saturation", 1.0],
        )
        assert config.fill == {"saturation": 1.0}

    def test_config_fill_from_dict(self) -> None:
        """Config accepts fill as dict directly."""
        config = ComposeNode.Config(
            id="test",
            ports=["hue", "saturation"],
            fill={"saturation": 1.0},
        )
        assert config.fill == {"saturation": 1.0}

    def test_config_requires_at_least_one_port(self) -> None:
        """Config requires at least one port."""
        with pytest.raises(ValueError):
            ComposeNode.Config(id="test", ports=[])


class TestComposeNodePorts:
    """Tests for ComposeNode port creation."""

    def test_creates_input_ports_from_config(self) -> None:
        """Node creates input ports matching config."""
        config = ComposeNode.Config(
            id="test",
            ports=["hue", "saturation", "lightness"],
        )
        node = ComposeNode(config)

        assert "hue" in node.inputs
        assert "saturation" in node.inputs
        assert "lightness" in node.inputs
        assert len(list(node.inputs)) == 3

    def test_input_ports_are_variable_length(self) -> None:
        """All input ports have variable channel count."""
        config = ComposeNode.Config(
            id="test",
            ports=["a", "b"],
        )
        node = ComposeNode(config)

        for port_name in ["a", "b"]:
            spec = node.inputs.get(port_name)
            assert spec is not None
            assert spec.is_variable

    def test_has_single_output_port(self) -> None:
        """Node has single 'out' output port."""
        config = ComposeNode.Config(
            id="test",
            ports=["a"],
        )
        node = ComposeNode(config)

        assert "out" in node.outputs
        assert len(list(node.outputs)) == 1


class TestComposeNodeValidation:
    """Tests for ComposeNode connection validation."""

    def test_validates_all_ports_connected_or_filled(self) -> None:
        """Validation passes when all ports have connection or fill."""
        config = ComposeNode.Config(
            id="compose",
            ports=["hue", "saturation", "lightness"],
            fill={"saturation": 1.0, "lightness": 0.5},
        )
        node = ComposeNode(config)

        # hue has connection, others have fill
        edges = [Edge(source="sine", source_port="dmx", target="compose", target_port="hue")]
        node.validate_connections(edges)  # Should not raise

    def test_fails_when_port_missing_connection_and_fill(self) -> None:
        """Validation fails when port has neither connection nor fill."""
        config = ComposeNode.Config(
            id="compose",
            ports=["hue", "saturation", "lightness"],
            fill={"lightness": 0.5},  # saturation missing!
        )
        node = ComposeNode(config)

        edges = [Edge(source="sine", source_port="dmx", target="compose", target_port="hue")]

        with pytest.raises(ValueError, match="saturation.*no connection.*no fill"):
            node.validate_connections(edges)

    def test_accepts_all_filled_no_connections(self) -> None:
        """Validation passes when all ports have fill values."""
        config = ComposeNode.Config(
            id="compose",
            ports=["a", "b", "c"],
            fill={"a": 0.1, "b": 0.2, "c": 0.3},
        )
        node = ComposeNode(config)

        node.validate_connections([])  # No edges, all filled

    def test_accepts_all_connected_no_fills(self) -> None:
        """Validation passes when all ports have connections."""
        config = ComposeNode.Config(
            id="compose",
            ports=["a", "b"],
        )
        node = ComposeNode(config)

        edges = [
            Edge(source="src1", source_port="out", target="compose", target_port="a"),
            Edge(source="src2", source_port="out", target="compose", target_port="b"),
        ]
        node.validate_connections(edges)


class TestComposeNodeHandle:
    """Tests for ComposeNode frame handling."""

    @pytest.fixture
    def compose_node(self) -> ComposeNode:
        """Create a 3-port compose node with fills for sat/light."""
        config = ComposeNode.Config(
            id="compose",
            ports=["hue", "saturation", "lightness"],
            fill={"saturation": 1.0, "lightness": 0.5},
        )
        return ComposeNode(config)

    @pytest.mark.anyio
    async def test_interleaves_output(self, compose_node: ComposeNode) -> None:
        """Output is correctly interleaved."""
        # Mock context that captures emitted frames
        emitted: list[Frame] = []

        class MockContext:
            async def emit(self, port: str, frame: Frame) -> None:
                emitted.append(frame)

        ctx = MockContext()

        # Send hue data: [0.1, 0.2, 0.3]
        hue_data = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        frame = Frame(
            topic="test",
            timestamp=0.0,
            payload=ArrayPayload(hue_data),
        )

        await compose_node.handle("hue", frame, ctx)  # type: ignore

        assert len(emitted) == 1
        out = np.asarray(emitted[0].payload, dtype=np.float32)

        # Expected: [h0, s0, l0, h1, s1, l1, h2, s2, l2]
        # = [0.1, 1.0, 0.5, 0.2, 1.0, 0.5, 0.3, 1.0, 0.5]
        expected = np.array(
            [0.1, 1.0, 0.5, 0.2, 1.0, 0.5, 0.3, 1.0, 0.5],
            dtype=np.float32,
        )
        np.testing.assert_array_almost_equal(out, expected)

    @pytest.mark.anyio
    async def test_ignores_unknown_ports(self, compose_node: ComposeNode) -> None:
        """Frames on unknown ports are ignored."""
        emitted: list[Frame] = []

        class MockContext:
            async def emit(self, port: str, frame: Frame) -> None:
                emitted.append(frame)

        ctx = MockContext()

        frame = Frame(
            topic="test",
            timestamp=0.0,
            payload=ArrayPayload(np.array([1.0], dtype=np.float32)),
        )

        await compose_node.handle("unknown_port", frame, ctx)  # type: ignore

        # No output since port is unknown and no length resolved
        assert len(emitted) == 0


class TestExtractBlockDictAccumulation:
    """Tests for repeated directive accumulation in config loader."""

    def test_accumulates_repeated_directives(self) -> None:
        """Repeated directives are accumulated as list-of-lists."""
        # Create Directive tree for:
        # fill saturation 1;
        # fill lightness 0.5;
        directive = Directive(
            keyword="node",
            args=(),
            block=(
                Directive("fill", ("saturation", "1"), (), 0),
                Directive("fill", ("lightness", "0.5"), (), 0),
            ),
            line=0,
        )

        result = _extract_config_dict(directive)

        assert "fill" in result
        assert result["fill"] == [["saturation", 1], ["lightness", 0.5]]

    def test_single_directive_not_wrapped(self) -> None:
        """Single directive is not wrapped in extra list."""
        directive = Directive(
            keyword="node",
            args=(),
            block=(
                Directive("fill", ("saturation", "1"), (), 0),
            ),
            line=0,
        )

        result = _extract_config_dict(directive)

        assert result["fill"] == ["saturation", 1]

    def test_nested_ports_block(self) -> None:
        """Nested ports block is extracted as list of names."""
        directive = Directive(
            keyword="node",
            args=(),
            block=(
                Directive(
                    keyword="ports",
                    args=(),
                    block=(
                        Directive("hue", (), (), 0),
                        Directive("saturation", (), (), 0),
                        Directive("lightness", (), (), 0),
                    ),
                    line=0,
                ),
            ),
            line=0,
        )

        result = _extract_config_dict(directive)

        assert "ports" in result
        # New loader extracts ports as list of names
        assert result["ports"] == ["hue", "saturation", "lightness"]


class TestComposeNodeIntegration:
    """Integration tests for ComposeNode with GraphBuilder."""

    def test_graph_validates_compose_connections(self) -> None:
        """GraphBuilder calls validate_connections on ComposeNode."""
        from rasl.nodes.sine_source import SineSourceNode

        # Create nodes
        sine_config = SineSourceNode.Config(id="sine", output_channels=10)
        sine = SineSourceNode(sine_config)

        compose_config = ComposeNode.Config(
            id="compose",
            ports=["hue", "saturation", "lightness"],
            fill={"saturation": 1.0, "lightness": 0.5},
        )
        compose = ComposeNode(compose_config)

        # Build graph
        builder = GraphBuilder()
        builder.add_node(sine)
        builder.add_node(compose)
        builder.connect("sine", "dmx", "compose", "hue")

        # Should succeed - hue connected, others filled
        plan = builder.build()
        assert "compose" in plan.nodes

    def test_graph_fails_on_missing_connection(self) -> None:
        """GraphBuilder fails when ComposeNode port lacks connection and fill."""
        from rasl.nodes.sine_source import SineSourceNode

        sine_config = SineSourceNode.Config(id="sine", output_channels=10)
        sine = SineSourceNode(sine_config)

        compose_config = ComposeNode.Config(
            id="compose",
            ports=["hue", "saturation", "lightness"],
            fill={"lightness": 0.5},  # saturation missing!
        )
        compose = ComposeNode(compose_config)

        builder = GraphBuilder()
        builder.add_node(sine)
        builder.add_node(compose)
        builder.connect("sine", "dmx", "compose", "hue")

        with pytest.raises(ValueError, match="saturation"):
            builder.build()
