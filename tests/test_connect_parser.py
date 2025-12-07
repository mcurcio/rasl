"""Tests for the connect directive parser."""

import pytest

from rasl.config import (
    ConnectParseError,
    ParsedConnect,
    ResolvedSlice,
    parse_connect,
    parse_connect_batch,
)


class TestResolvedSlice:
    """Tests for ResolvedSlice dataclass."""

    def test_single_channel(self) -> None:
        """Single channel slice has explicit end."""
        s = ResolvedSlice(start=5, end=6)
        assert s.start == 5
        assert s.end == 6
        assert not s.is_open
        assert s.length(None) == 1
        assert s.length(512) == 1

    def test_range_slice(self) -> None:
        """Range slice has explicit start and end."""
        s = ResolvedSlice(start=0, end=10)
        assert s.start == 0
        assert s.end == 10
        assert not s.is_open
        assert s.length(None) == 10
        assert s.length(512) == 10

    def test_open_ended_slice(self) -> None:
        """Open-ended slice has no end."""
        s = ResolvedSlice(start=5, end=None)
        assert s.start == 5
        assert s.end is None
        assert s.is_open
        assert s.length(None) is None  # Cannot determine
        assert s.length(512) == 507  # 512 - 5


class TestParseConnect:
    """Tests for parse_connect function."""

    def test_simple_node_reference(self) -> None:
        """Parse simple node reference."""
        result = parse_connect("upstream")
        assert result == ParsedConnect(
            source_node="upstream",
            source_port=None,
            source_slice=None,
            dest_port=None,
            dest_slice=None,
        )

    def test_node_with_port(self) -> None:
        """Parse node.port reference."""
        result = parse_connect("upstream.rgb")
        assert result == ParsedConnect(
            source_node="upstream",
            source_port="rgb",
            source_slice=None,
            dest_port=None,
            dest_slice=None,
        )

    def test_node_with_single_channel_slice(self) -> None:
        """Parse node[n] single channel slice."""
        result = parse_connect("upstream[5]")
        assert result.source_node == "upstream"
        assert result.source_port is None
        assert result.source_slice == ResolvedSlice(5, 6)

    def test_node_with_range_slice(self) -> None:
        """Parse node[start:end] range slice."""
        result = parse_connect("upstream[0:10]")
        assert result.source_node == "upstream"
        assert result.source_slice == ResolvedSlice(0, 10)

    def test_node_with_open_slice(self) -> None:
        """Parse node[start:] open-ended slice."""
        result = parse_connect("upstream[5:]")
        assert result.source_node == "upstream"
        assert result.source_slice == ResolvedSlice(5, None)
        assert result.source_slice.is_open

    def test_node_port_with_slice(self) -> None:
        """Parse node.port[slice] combination."""
        result = parse_connect("upstream.rgb[0:3]")
        assert result.source_node == "upstream"
        assert result.source_port == "rgb"
        assert result.source_slice == ResolvedSlice(0, 3)

    def test_with_dest_port(self) -> None:
        """Parse with destination port."""
        result = parse_connect("upstream input")
        assert result.source_node == "upstream"
        assert result.dest_port == "input"
        assert result.dest_slice is None

    def test_with_dest_port_and_slice(self) -> None:
        """Parse with destination port and slice."""
        result = parse_connect("upstream input[0:3]")
        assert result.source_node == "upstream"
        assert result.dest_port == "input"
        assert result.dest_slice == ResolvedSlice(0, 3)

    def test_full_specification(self) -> None:
        """Parse full source and dest specification."""
        result = parse_connect("upstream.rgb[0:3] color[6:9]")
        assert result == ParsedConnect(
            source_node="upstream",
            source_port="rgb",
            source_slice=ResolvedSlice(0, 3),
            dest_port="color",
            dest_slice=ResolvedSlice(6, 9),
        )

    def test_whitespace_handling(self) -> None:
        """Whitespace is handled correctly."""
        result = parse_connect("  upstream.rgb[0:3]   input[0:3]  ")
        assert result.source_node == "upstream"
        assert result.source_port == "rgb"
        assert result.dest_port == "input"

    def test_underscore_identifiers(self) -> None:
        """Identifiers can contain underscores."""
        result = parse_connect("my_node.my_port my_input")
        assert result.source_node == "my_node"
        assert result.source_port == "my_port"
        assert result.dest_port == "my_input"

    def test_numeric_suffix_identifiers(self) -> None:
        """Identifiers can have numeric suffixes."""
        result = parse_connect("node1.port2 input3")
        assert result.source_node == "node1"
        assert result.source_port == "port2"
        assert result.dest_port == "input3"


class TestParseConnectErrors:
    """Tests for parse_connect error handling."""

    def test_empty_string(self) -> None:
        """Empty string raises error."""
        with pytest.raises(ConnectParseError, match="Empty"):
            parse_connect("")

    def test_whitespace_only(self) -> None:
        """Whitespace-only string raises error."""
        with pytest.raises(ConnectParseError, match="Empty"):
            parse_connect("   ")

    def test_invalid_identifier_start(self) -> None:
        """Identifier starting with digit raises error."""
        with pytest.raises(ConnectParseError, match="Expected node identifier"):
            parse_connect("123node")

    def test_missing_port_after_dot(self) -> None:
        """Missing port after dot raises error."""
        with pytest.raises(ConnectParseError, match="Expected port identifier"):
            parse_connect("node.")

    def test_missing_slice_content(self) -> None:
        """Missing content in slice raises error."""
        with pytest.raises(ConnectParseError, match="Expected integer"):
            parse_connect("node[]")

    def test_negative_slice_index(self) -> None:
        """Negative slice index raises error (caught as invalid integer)."""
        # The parser reads integers, so -1 would be parsed as identifier fail
        with pytest.raises(ConnectParseError):
            parse_connect("node[-1]")

    def test_slice_end_less_than_start(self) -> None:
        """Slice end < start raises error."""
        with pytest.raises(ConnectParseError, match="must be >= start"):
            parse_connect("node[5:3]")

    def test_unclosed_slice(self) -> None:
        """Unclosed slice bracket raises error."""
        with pytest.raises(ConnectParseError, match="Expected"):
            parse_connect("node[0:3")

    def test_trailing_garbage(self) -> None:
        """Trailing garbage raises error."""
        with pytest.raises(ConnectParseError, match="Unexpected characters"):
            parse_connect("upstream input extra")


class TestParseConnectBatch:
    """Tests for parse_connect_batch function."""

    def test_empty_list(self) -> None:
        """Empty list returns empty results."""
        result = parse_connect_batch([])
        assert result == []

    def test_multiple_valid(self) -> None:
        """Multiple valid directives are parsed."""
        result = parse_connect_batch([
            "upstream",
            "other.port",
            "third[0:3] input[0:3]",
        ])
        assert len(result) == 3
        assert result[0].source_node == "upstream"
        assert result[1].source_port == "port"
        assert result[2].dest_port == "input"

    def test_batch_error_includes_index(self) -> None:
        """Batch error includes index of failing directive."""
        with pytest.raises(ConnectParseError, match=r"\[1\]"):
            parse_connect_batch([
                "valid",
                "",  # Invalid
                "also_valid",
            ])
