"""Tests for ComposeNode."""

import pytest

from rasl.config.document import Directive, parse_document
from rasl.config.node_directive import _extract_config_dict
from rasl.graph import Edge, GraphBuilder
from rasl.nodes.color.compose_node import ComposeNode


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
            port = node.inputs.get(port_name)
            # Variable-length ports have no fixed channel count
            assert port.count is None

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


def _directive(text: str) -> Directive:
    """The one directive `text` holds."""
    return parse_document(text).block[0]


class TestExtractBlockDictAccumulation:
    """Tests for repeated directive accumulation in config loader."""

    def test_accumulates_repeated_directives(self) -> None:
        """Repeated directives are accumulated as list-of-lists."""
        directive = _directive("node { fill saturation 1; fill lightness 0.5; }")

        result = _extract_config_dict(directive)

        assert "fill" in result
        assert result["fill"] == [["saturation", 1], ["lightness", 0.5]]

    def test_single_directive_not_wrapped(self) -> None:
        """Single directive is not wrapped in extra list."""
        directive = _directive("node { fill saturation 1; }")

        result = _extract_config_dict(directive)

        assert result["fill"] == ["saturation", 1]

    def test_nested_ports_block(self) -> None:
        """A block of bare names reads like any block; ComposeNode's Config takes the names."""
        directive = _directive("node { ports { hue; saturation; lightness; } }")

        result = _extract_config_dict(directive)

        assert "ports" in result
        assert list(result["ports"]) == ["hue", "saturation", "lightness"]
        assert ComposeNode.Config(id="c", ports=result["ports"], fill={"hue": 0}).ports == ["hue", "saturation", "lightness"]


class TestComposeNodeIntegration:
    """Integration tests for ComposeNode with GraphBuilder."""

    def test_graph_validates_compose_connections(self) -> None:
        """GraphBuilder calls validate_connections on ComposeNode."""
        from rasl.nodes.debug.sine_source import SineSourceNode

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
        from rasl.nodes.debug.sine_source import SineSourceNode

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
