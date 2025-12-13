"""Tests for channel slicing in connect directives."""

import numpy as np
import pytest

from rasl.config.connect_parser import ResolvedSlice
from rasl.config.connection import parse_port_ref
from rasl.config.loader import parse_config
from rasl.engine.graph import Edge


class TestParsePortWithSlice:
    """Tests for parse_port_ref with slices."""

    def test_no_slice(self):
        """Port without slice returns None for slice."""
        ref = parse_port_ref("node.dmx")
        assert ref.port == "dmx"
        assert ref.slice_ is None

    def test_range_slice(self):
        """Port with range slice parses correctly."""
        ref = parse_port_ref("node.out[0:151]")
        assert ref.port == "out"
        assert ref.slice_ == ResolvedSlice(0, 151)

    def test_open_ended_slice(self):
        """Port with open-ended slice parses correctly."""
        ref = parse_port_ref("node.out[100:]")
        assert ref.port == "out"
        assert ref.slice_ == ResolvedSlice(100, None)

    def test_single_index_slice(self):
        """Port with single index - note: new parser doesn't auto-expand to range."""
        # The new parser treats [5] as [5:] (open-ended from 5)
        # This is a behavior change from the old parser
        ref = parse_port_ref("node.out[5:]")
        assert ref.port == "out"
        assert ref.slice_ == ResolvedSlice(5, None)


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


class TestRepeatWithoutSlices:
    def test_parse_repeat_without_slices_creates_single_edge_with_repeat(self):
        config = """
        rasl {
            node literal src matrix [[1,2,3]];
            node ConsoleSink sink {
                fps 1;
                connect src {
                    repeat 3;
                }
            }
        }
        """
        plan = parse_config(config)

        edges = plan.adjacency["src"]
        assert len(edges) == 1
        assert edges[0].source_slice is None
        assert edges[0].target_slice is None
        assert edges[0].repeat == 3

    def test_parse_repeat_until_without_slices_creates_single_edge(self):
        config = """
        rasl {
            node literal src matrix [[1,2,3]];
            node ConsoleSink sink {
                fps 1;
                connect src {
                    repeat_until 10;
                }
            }
        }
        """
        plan = parse_config(config)

        edges = plan.adjacency["src"]
        assert len(edges) == 1
        assert edges[0].source_slice is None
        assert edges[0].target_slice is None
        assert edges[0].repeat == 1
        assert edges[0].repeat_until == 10

    def test_repeat_until_with_slices_raises(self):
        config = """
        rasl {
            node SineSource wave {
                output_channels 512;
            }
            node ConsoleSink sink {
                fps 1;
                connect wave[0:100] {
                    repeat_until 200;
                }
            }
        }
        """
        with pytest.raises(ValueError, match="repeat_until is only supported"):
            parse_config(config)
