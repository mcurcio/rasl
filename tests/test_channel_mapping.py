"""Tests for channel mapping and overlap detection."""

import pytest

from rasl.config import (
    ChannelMapping,
    ChannelOverlapError,
    PortChannelRegistry,
)


class TestChannelMapping:
    """Tests for ChannelMapping dataclass."""

    def test_basic_mapping(self) -> None:
        """Create a basic channel mapping."""
        m = ChannelMapping(
            source_node="source",
            source_port="output",
            source_start=0,
            dest_port="input",
            dest_start=0,
            length=10,
        )
        assert m.source_node == "source"
        assert m.source_port == "output"
        assert m.source_start == 0
        assert m.dest_port == "input"
        assert m.dest_start == 0
        assert m.length == 10

    def test_source_end(self) -> None:
        """source_end is computed correctly."""
        m = ChannelMapping(
            source_node="s",
            source_port="p",
            source_start=5,
            dest_port="i",
            dest_start=0,
            length=10,
        )
        assert m.source_end == 15

    def test_dest_end(self) -> None:
        """dest_end is computed correctly."""
        m = ChannelMapping(
            source_node="s",
            source_port="p",
            source_start=0,
            dest_port="i",
            dest_start=100,
            length=50,
        )
        assert m.dest_end == 150

    def test_source_channels(self) -> None:
        """source_channels returns correct range."""
        m = ChannelMapping(
            source_node="s",
            source_port="p",
            source_start=5,
            dest_port="i",
            dest_start=0,
            length=3,
        )
        assert list(m.source_channels()) == [5, 6, 7]

    def test_dest_channels(self) -> None:
        """dest_channels returns correct range."""
        m = ChannelMapping(
            source_node="s",
            source_port="p",
            source_start=0,
            dest_port="i",
            dest_start=10,
            length=3,
        )
        assert list(m.dest_channels()) == [10, 11, 12]

    def test_frozen(self) -> None:
        """ChannelMapping is immutable."""
        m = ChannelMapping(
            source_node="s",
            source_port="p",
            source_start=0,
            dest_port="i",
            dest_start=0,
            length=1,
        )
        with pytest.raises(AttributeError):
            m.length = 5  # type: ignore


class TestPortChannelRegistry:
    """Tests for PortChannelRegistry overlap detection."""

    def test_single_assignment(self) -> None:
        """Single assignment succeeds."""
        registry = PortChannelRegistry()
        registry.assign(
            dest_node="sink",
            dest_port="input",
            dest_channel=0,
            source_node="source",
            source_port="output",
            source_channel=0,
        )
        assert len(registry) == 1

    def test_multiple_non_overlapping(self) -> None:
        """Multiple non-overlapping assignments succeed."""
        registry = PortChannelRegistry()
        registry.assign("sink", "input", 0, "source1", "output", 0)
        registry.assign("sink", "input", 1, "source1", "output", 1)
        registry.assign("sink", "input", 2, "source2", "output", 0)
        assert len(registry) == 3

    def test_different_ports_no_overlap(self) -> None:
        """Same channel on different ports is not an overlap."""
        registry = PortChannelRegistry()
        registry.assign("sink", "input1", 0, "source", "output", 0)
        registry.assign("sink", "input2", 0, "source", "output", 1)
        assert len(registry) == 2

    def test_different_nodes_no_overlap(self) -> None:
        """Same channel on different nodes is not an overlap."""
        registry = PortChannelRegistry()
        registry.assign("sink1", "input", 0, "source", "output", 0)
        registry.assign("sink2", "input", 0, "source", "output", 1)
        assert len(registry) == 2

    def test_overlap_raises_error(self) -> None:
        """Overlapping assignment raises ChannelOverlapError."""
        registry = PortChannelRegistry()
        registry.assign("sink", "input", 0, "source1", "output", 0)

        with pytest.raises(ChannelOverlapError) as exc_info:
            registry.assign("sink", "input", 0, "source2", "output", 5)

        err = exc_info.value
        assert err.dest_node == "sink"
        assert err.dest_port == "input"
        assert err.dest_channel == 0
        assert err.existing_source == ("source1", "output", 0)
        assert err.new_source == ("source2", "output", 5)

    def test_overlap_error_message(self) -> None:
        """Overlap error has descriptive message."""
        registry = PortChannelRegistry()
        registry.assign("sink", "input", 5, "nodeA", "out", 10)

        with pytest.raises(ChannelOverlapError, match="sink.input\\[5\\]"):
            registry.assign("sink", "input", 5, "nodeB", "out", 20)

    def test_assign_mapping(self) -> None:
        """assign_mapping registers all channels in mapping."""
        registry = PortChannelRegistry()
        mapping = ChannelMapping(
            source_node="source",
            source_port="output",
            source_start=0,
            dest_port="input",
            dest_start=10,
            length=5,
        )
        registry.assign_mapping("sink", mapping)
        assert len(registry) == 5

    def test_assign_mapping_overlap(self) -> None:
        """assign_mapping detects overlap with existing assignments."""
        registry = PortChannelRegistry()
        registry.assign("sink", "input", 12, "other", "out", 0)

        mapping = ChannelMapping(
            source_node="source",
            source_port="output",
            source_start=0,
            dest_port="input",
            dest_start=10,
            length=5,  # Covers channels 10-14, overlaps with 12
        )

        with pytest.raises(ChannelOverlapError, match="input\\[12\\]"):
            registry.assign_mapping("sink", mapping)

    def test_clear(self) -> None:
        """clear removes all assignments."""
        registry = PortChannelRegistry()
        registry.assign("sink", "input", 0, "source", "output", 0)
        registry.assign("sink", "input", 1, "source", "output", 1)
        assert len(registry) == 2

        registry.clear()
        assert len(registry) == 0

        # Can now assign to previously occupied channels
        registry.assign("sink", "input", 0, "new_source", "output", 0)
        assert len(registry) == 1
