"""Tests for channel slicing in connect directives."""

import numpy as np
import pytest

from rasl.config.connect_parser import ResolvedSlice
from rasl.config.loader import parse_config, ParsedConnection, _parse_port_with_slice
from rasl.engine.graph import Edge


class TestParsePortWithSlice:
    """Tests for _parse_port_with_slice helper."""

    def test_no_slice(self):
        """Port without slice returns None for slice."""
        port, slice_spec = _parse_port_with_slice("dmx")
        assert port == "dmx"
        assert slice_spec is None

    def test_range_slice(self):
        """Port with range slice parses correctly."""
        port, slice_spec = _parse_port_with_slice("out[0:151]")
        assert port == "out"
        assert slice_spec == ResolvedSlice(0, 151)

    def test_open_ended_slice(self):
        """Port with open-ended slice parses correctly."""
        port, slice_spec = _parse_port_with_slice("out[100:]")
        assert port == "out"
        assert slice_spec == ResolvedSlice(100, None)

    def test_single_index_slice(self):
        """Port with single index becomes range of 1."""
        port, slice_spec = _parse_port_with_slice("out[5]")
        assert port == "out"
        assert slice_spec == ResolvedSlice(5, 6)


class TestEdgeWithSlices:
    """Tests for Edge dataclass with slice fields."""

    def test_edge_without_slices(self):
        """Edge without slices has None for slice fields."""
        edge = Edge(
            source="sine",
            source_port="dmx",
            target="console",
            target_port="dmx",
        )
        assert edge.source_slice is None
        assert edge.target_slice is None

    def test_edge_with_slices(self):
        """Edge with slices stores them correctly."""
        edge = Edge(
            source="twinkle",
            source_port="out",
            target="sink",
            target_port="universe0",
            source_slice=ResolvedSlice(0, 151),
            target_slice=ResolvedSlice(0, 151),
        )
        assert edge.source_slice == ResolvedSlice(0, 151)
        assert edge.target_slice == ResolvedSlice(0, 151)


class TestConfigParserWithSlices:
    """Tests for config parsing with channel slices."""

    def test_parse_sliced_connect(self):
        """Test parsing connect with channel slices."""
        config = """
        rasl {
            node SineSource sine {
                output_channels 512;
            }
            node ConsoleSink console {
                input_port dmx;
            }
            connect sine[0:100] console.dmx[0:100];
        }
        """
        plan = parse_config(config)

        # Check that the edge has slice info
        assert len(plan.adjacency["sine"]) == 1
        edge = plan.adjacency["sine"][0]
        assert edge.source == "sine"
        assert edge.source_port == "dmx"  # Default port
        assert edge.source_slice == ResolvedSlice(0, 100)
        assert edge.target == "console"
        assert edge.target_port == "dmx"
        assert edge.target_slice == ResolvedSlice(0, 100)

    def test_parse_nested_sliced_connect(self):
        """Test parsing nested connect with channel slices."""
        config = """
        rasl {
            node SineSource sine {
                output_channels 512;
            }
            node ConsoleSink console {
                input_port dmx;
                connect sine[50:150] dmx[0:100];
            }
        }
        """
        plan = parse_config(config)

        edge = plan.adjacency["sine"][0]
        assert edge.source_slice == ResolvedSlice(50, 150)
        assert edge.target_slice == ResolvedSlice(0, 100)

    def test_parse_multiple_sliced_connects(self):
        """Test parsing multiple sliced connects to same target."""
        config = """
        rasl {
            node SineSource sine {
                output_channels 512;
            }
            node ConsoleSink console {
                input_port dmx;
                connect sine[0:100] dmx[0:100];
                connect sine[0:100] dmx[100:200];
            }
        }
        """
        plan = parse_config(config)

        edges = plan.adjacency["sine"]
        assert len(edges) == 2

        # First edge
        assert edges[0].source_slice == ResolvedSlice(0, 100)
        assert edges[0].target_slice == ResolvedSlice(0, 100)

        # Second edge
        assert edges[1].source_slice == ResolvedSlice(0, 100)
        assert edges[1].target_slice == ResolvedSlice(100, 200)
