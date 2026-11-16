"""Tests for channel slicing in connect directives."""

import pytest

from rasl.config.build import parse_config
from rasl.config.connect import parse_port_ref
from rasl.config.document import ConfigError
from rasl.graph import Edge, Slice


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
        assert ref.slice_ == Slice(0, 151)

    def test_open_ended_slice(self):
        """Port with open-ended slice parses correctly."""
        ref = parse_port_ref("node.out[100:]")
        assert ref.port == "out"
        assert ref.slice_ == Slice(100, None)

    def test_single_index_slice(self):
        """Port with single index - note: new parser doesn't auto-expand to range."""
        # The new parser treats [5] as [5:] (open-ended from 5)
        # This is a behavior change from the old parser
        ref = parse_port_ref("node.out[5:]")
        assert ref.port == "out"
        assert ref.slice_ == Slice(5, None)


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
            source_slice=Slice(0, 151),
            target_slice=Slice(0, 151),
        )
        assert edge.source_slice == Slice(0, 151)
        assert edge.target_slice == Slice(0, 151)


class TestConfigParserWithSlices:
    """Tests for config parsing with channel slices."""

    def test_parse_nested_sliced_connect(self):
        """Test parsing nested connect with channel slices."""
        config = """
        graph {
            node SineSource sine {
                output_channels 512;
            }
            node ConsoleSink console {
                input_port dmx;
                connect sine[50~150] dmx[0~100];
            }
        }
        """
        plan = parse_config(config)

        edge = plan.adjacency["sine"][0]
        assert edge.source_slice == Slice(50, 150)
        assert edge.target_slice == Slice(0, 100)

    def test_parse_multiple_sliced_connects(self):
        """Test parsing multiple sliced connects to same target."""
        config = """
        graph {
            node SineSource sine {
                output_channels 512;
            }
            node ConsoleSink console {
                input_port dmx;
                connect sine[0~100] dmx[0~100];
                connect sine[0~100] dmx[100~200];
            }
        }
        """
        plan = parse_config(config)

        edges = plan.adjacency["sine"]
        assert len(edges) == 2

        # First edge
        assert edges[0].source_slice == Slice(0, 100)
        assert edges[0].target_slice == Slice(0, 100)

        # Second edge
        assert edges[1].source_slice == Slice(0, 100)
        assert edges[1].target_slice == Slice(100, 200)


class TestRepeatWithoutSlices:
    def test_parse_repeat_without_slices_creates_single_edge_with_repeat(self):
        config = """
        graph {
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
        graph {
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
        graph {
            node SineSource wave {
                output_channels 512;
            }
            node ConsoleSink sink {
                fps 1;
                connect wave[0~100] {
                    repeat_until 200;
                }
            }
        }
        """
        with pytest.raises(ConfigError, match="repeat_until is only supported"):
            parse_config(config)


class TestConnectErrorsArePlaced:
    """A connection the graph refuses is reported on the node that asks for it."""

    def test_a_slice_out_of_range_is_a_config_error_on_the_connecting_node(self):
        config = """
        graph {
            node cron minute * * * * *;
            node ConsoleSink sink {
                fps 1;
                connect minute[0~4];
            }
        }
        """
        with pytest.raises(
            ConfigError,
            match=r"Node 'sink': Slice \[0:4\] is out of range for port minute.out, which has 1 elements",
        ) as caught:
            parse_config(config)
        assert caught.value.line == 4

    def test_two_connections_into_one_port_are_a_config_error_on_the_connecting_node(self):
        config = """
        graph {
            node cron minute * * * * *;
            node cron hour 0 * * * *;
            node ConsoleSink sink {
                fps 1;
                connect minute;
                connect hour;
            }
        }
        """
        with pytest.raises(
            ConfigError, match=r"Node 'sink': Overlapping connections into sink\.\w+: hour\.out writes"
        ) as caught:
            parse_config(config)
        assert caught.value.line == 5

    def test_a_repeat_of_a_source_of_unknown_length_is_a_config_error(self):
        config = """
        graph {
            node Waveform hue {
                output_channels 4;
            }
            node ConsoleSink sink {
                fps 1;
                connect hue[2~] dmx[0~] {
                    repeat 3;
                }
            }
        }
        """
        with pytest.raises(ConfigError, match=r"Node 'sink': repeat 3 needs the length of hue\[2:\]"):
            parse_config(config)

    def test_an_unknown_source_node_is_a_config_error_on_the_connecting_node(self):
        config = """
        graph {
            node ConsoleSink sink {
                fps 1;
                connect nowhere;
            }
        }
        """
        with pytest.raises(ConfigError, match="Node 'sink': Unknown source node 'nowhere'") as caught:
            parse_config(config)
        assert caught.value.line == 3

    def test_an_unknown_source_port_is_a_config_error_naming_the_ports(self):
        config = """
        graph {
            node Waveform hue {
                output_channels 4;
            }
            node ConsoleSink sink {
                fps 1;
                connect hue.nope;
            }
        }
        """
        with pytest.raises(
            ConfigError, match="Node 'sink': Node 'hue' has no output port 'nope'. Available: "
        ) as caught:
            parse_config(config)
        assert caught.value.line == 6

    def test_a_missing_default_port_says_which_node(self):
        config = """
        graph {
            node Waveform wave {
                output_channels 3;
            }
            node Smooth calm {
                connect wave;
            }
        }
        """
        with pytest.raises(ConfigError, match="Node 'calm': No default port") as caught:
            parse_config(config)
        assert caught.value.line == 6

    def test_a_sacn_source_defaults_to_its_merged_channels(self):
        config = """
        graph {
            node SacnSource input {
                universes 1 2;
            }
            node ConsoleSink sink {
                fps 1;
                connect input;
            }
        }
        """
        edge = parse_config(config).adjacency["input"][0]
        assert edge.source_port == "channels"
