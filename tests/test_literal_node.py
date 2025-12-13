"""Tests for LiteralNode."""

import numpy as np
import pytest

from rasl.config.loader import parse_config
from rasl.config.dispatch import ConfigError
from rasl.nodes.literal_node import LiteralNode, parse_literal, build_payload
from rasl.engine.frames import ColorPayload, MatrixPayload


class TestParseLiteral:
    """Tests for parse_literal function."""

    def test_parse_nested_list(self) -> None:
        """Test parsing nested list."""
        result = parse_literal("[[1, 0, 0], [0.5, 0, 0], [0.3, 0, 0]]")
        assert result == [[1, 0, 0], [0.5, 0, 0], [0.3, 0, 0]]

    def test_parse_flat_list(self) -> None:
        """Test parsing flat list."""
        result = parse_literal("[1.0, 0.9, 0.8]")
        assert result == [1.0, 0.9, 0.8]

    def test_parse_string(self) -> None:
        """Test parsing quoted string."""
        result = parse_literal('"hello"')
        assert result == "hello"

    def test_parse_number(self) -> None:
        """Test parsing number."""
        assert parse_literal("42") == 42
        assert parse_literal("3.14") == 3.14
        assert parse_literal("-0.5") == -0.5

    def test_parse_boolean(self) -> None:
        """Test parsing boolean variants."""
        assert parse_literal("true") is True
        assert parse_literal("True") is True
        assert parse_literal("false") is False
        assert parse_literal("off") is False

    def test_parse_none(self) -> None:
        """Test parsing none/null."""
        assert parse_literal("none") is None
        assert parse_literal("null") is None
        assert parse_literal("None") is None

    def test_parse_invalid(self) -> None:
        """Test parsing invalid literal raises ValueError."""
        with pytest.raises(ValueError, match="Cannot parse literal"):
            parse_literal("not a valid literal")


class TestBuildPayload:
    """Tests for build_payload function."""

    def test_build_color_payload_2d(self) -> None:
        """Test building color payload from 2D list."""
        payload = build_payload("color", "hsl", [[1, 0, 0], [0.5, 0, 0], [0.3, 0, 0]])
        assert isinstance(payload, ColorPayload)
        assert payload.model == "hsl"
        assert payload.data.shape == (3, 3)

    def test_build_color_payload_1d(self) -> None:
        """Test building color payload from 1D list (single color)."""
        payload = build_payload("color", "okhsl", [0.1, 0.8, 0.65])
        assert isinstance(payload, ColorPayload)
        assert payload.model == "okhsl"
        assert payload.data.shape == (1, 3)

    def test_build_color_payload_default_model(self) -> None:
        """Test color payload defaults to srgb model."""
        payload = build_payload("color", None, [[1, 0, 0]])
        assert payload.model == "srgb"

    def test_build_matrix_payload(self) -> None:
        """Test building matrix payload."""
        payload = build_payload("matrix", None, [1.0, 0.9, 0.8, 0.7])
        assert isinstance(payload, MatrixPayload)
        assert payload.data.shape == (4, 1)
        np.testing.assert_array_almost_equal(payload.data[:, 0], [1.0, 0.9, 0.8, 0.7])

    def test_build_unknown_kind(self) -> None:
        """Test unknown payload kind raises ValueError."""
        with pytest.raises(ValueError, match="Unknown literal payload kind"):
            build_payload("unknown", None, [1, 2, 3])


class TestLiteralNodeConfig:
    """Tests for LiteralNode config parsing."""

    def test_parse_color_literal(self) -> None:
        """Test parsing color literal from config."""
        config = """
        rasl {
            node literal static_hsl color:hsl [[1, 0, 0], [0.5, 0, 0], [0.3, 0, 0]];
        }
        """
        plan = parse_config(config)
        assert "static_hsl" in plan.nodes
        node = plan.nodes["static_hsl"]
        assert isinstance(node, LiteralNode)
        assert isinstance(node._payload, ColorPayload)
        assert node._payload.model == "hsl"

    def test_parse_matrix_literal(self) -> None:
        """Test parsing matrix literal from config."""
        config = """
        rasl {
            node literal gains matrix [[1.0, 0.9, 0.8, 0.7]];
        }
        """
        plan = parse_config(config)
        node = plan.nodes["gains"]
        assert isinstance(node._payload, MatrixPayload)

    def test_parse_color_without_subtype(self) -> None:
        """Test parsing color literal without subtype defaults to srgb."""
        config = """
        rasl {
            node literal rgb_color color [[1, 0, 0]];
        }
        """
        plan = parse_config(config)
        node = plan.nodes["rgb_color"]
        assert node._payload.model == "srgb"

    def test_parse_literal_missing_value(self) -> None:
        """Test literal node without value raises error."""
        config = """
        rasl {
            node literal test color:hsl;
        }
        """
        with pytest.raises(ConfigError, match="literal node requires"):
            parse_config(config)

    def test_literal_connected_to_sink(self) -> None:
        """Test literal node can be connected to a sink."""
        config = """
        rasl {
            node literal static_hsl color:hsl [[1, 0, 0], [0.5, 0, 0]];
            node ConsoleSink console {
                fps 1;
                connect static_hsl;
            }
        }
        """
        plan = parse_config(config)
        assert "static_hsl" in plan.nodes
        assert "console" in plan.nodes
        # Check adjacency shows connection
        assert "static_hsl" in plan.adjacency
