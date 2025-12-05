"""Unit tests for the configuration loader."""

import tempfile
from pathlib import Path

import pytest

from rasl.config.loader import ConfigError, load_config, parse_config
from rasl.nodes import (
    ConsoleSinkNode,
    SacnSinkNode,
    SacnSourceNode,
    SineSourceNode,
    UniversePatchTransform,
)


class TestParseConfig:
    """Tests for parse_config function."""

    def test_parse_simple_source(self) -> None:
        """Test parsing a simple source node config."""
        config = """
        rasl {
            node sacnSource {
                type SacnSourceNode;
                universes 1 2;
            }
        }
        """
        plan = parse_config(config)

        assert len(plan.nodes) == 1
        assert "sacnSource" in plan.nodes
        node = plan.nodes["sacnSource"]
        assert isinstance(node, SacnSourceNode)

    def test_parse_source_with_metadata(self) -> None:
        """Test parsing source node with metadata."""
        config = """
        rasl {
            node source {
                type SacnSourceNode;
                universes 1;
                metadata "colorSpace=rgb";
            }
        }
        """
        plan = parse_config(config)
        node = plan.nodes["source"]
        assert isinstance(node, SacnSourceNode)

    def test_parse_transform_with_segments(self) -> None:
        """Test parsing transform node with segments."""
        config = """
        rasl {
            node patch {
                type UniversePatchTransform;
                output universe0;
                segment {
                    source_universe 1;
                    source_channel 1;
                    length 150;
                    target_channel 1;
                }
            }
        }
        """
        plan = parse_config(config)

        assert "patch" in plan.nodes
        node = plan.nodes["patch"]
        assert isinstance(node, UniversePatchTransform)
        assert node.outputs == ("universe0",)

    def test_parse_transform_with_defaults(self) -> None:
        """Test parsing transform with defaults block."""
        config = """
        rasl {
            node patch {
                type UniversePatchTransform;
                output out;
                defaults {
                    source_universe 2;
                    source_channel 1;
                    length 100;
                }
                segment { target_channel 1; }
                segment { target_channel 101; }
            }
        }
        """
        plan = parse_config(config)
        node = plan.nodes["patch"]
        assert isinstance(node, UniversePatchTransform)

    def test_parse_sink_node(self) -> None:
        """Test parsing sink node."""
        config = """
        rasl {
            node sink {
                type SacnSinkNode;
                input universe0;
                target_host "10.0.60.30";
                target_universe 0;
                min_interval_ms 25;
            }
        }
        """
        plan = parse_config(config)

        assert "sink" in plan.nodes
        node = plan.nodes["sink"]
        assert isinstance(node, SacnSinkNode)

    def test_parse_edges(self) -> None:
        """Test parsing edge connections."""
        config = """
        rasl {
            node source {
                type SacnSourceNode;
                universes 1;
            }
            node patch {
                type UniversePatchTransform;
                output out;
                segment { source_universe 1; source_channel 1; length 100; target_channel 1; }
            }
            edge { from source:dmx; to patch:dmx; }
        }
        """
        plan = parse_config(config)

        assert len(plan.adjacency["source"]) == 1
        edge = plan.adjacency["source"][0]
        assert edge.source == "source"
        assert edge.source_port == "dmx"
        assert edge.target == "patch"
        assert edge.target_port == "dmx"

    def test_parse_full_pipeline(self) -> None:
        """Test parsing a complete source -> transform -> sink pipeline."""
        config = """
        rasl {
            node sacnSource {
                type SacnSourceNode;
                universes 1 2;
            }
            node patch {
                type UniversePatchTransform;
                output universe0;
                segment { source_universe 1; source_channel 1; length 150; target_channel 1; }
            }
            node sink {
                type SacnSinkNode;
                input universe0;
                target_host "10.0.60.30";
                target_universe 0;
            }
            edge { from sacnSource:dmx; to patch:dmx; }
            edge { from patch:universe0; to sink:universe0; }
        }
        """
        plan = parse_config(config)

        assert len(plan.nodes) == 3
        assert plan.topological_order == ("sacnSource", "patch", "sink")

    def test_parse_no_rasl_block_raises(self) -> None:
        """Test that missing rasl block raises ConfigError."""
        config = """
        other {
            node foo {}
        }
        """
        with pytest.raises(ConfigError, match="No 'rasl' block"):
            parse_config(config)

    def test_parse_unknown_node_type_raises(self) -> None:
        """Test that unknown node type raises ConfigError."""
        config = """
        rasl {
            node foo {
                type UnknownNodeType;
            }
        }
        """
        with pytest.raises(ConfigError, match="Unknown node type"):
            parse_config(config)

    def test_parse_sink_missing_target_host_raises(self) -> None:
        """Test that sink without target_host raises ConfigError."""
        config = """
        rasl {
            node sink {
                type SacnSinkNode;
                input in;
                target_universe 0;
            }
        }
        """
        with pytest.raises(ConfigError, match="requires target_host"):
            parse_config(config)

    def test_parse_transform_no_segments_raises(self) -> None:
        """Test that transform without segments raises ConfigError."""
        config = """
        rasl {
            node patch {
                type UniversePatchTransform;
                output out;
            }
        }
        """
        with pytest.raises(ConfigError, match="requires at least one segment"):
            parse_config(config)

    def test_parse_sine_source_node(self) -> None:
        config = """
        rasl {
            node SineSource sine {
                outputs 10;
                frequency_hz 2.0;
                fps 20;
                amplitude 0.25;
                offset 0.75;
                metadata "colorSpace=rgb";
            }
        }
        """
        plan = parse_config(config)

        assert "sine" in plan.nodes
        node = plan.nodes["sine"]
        assert isinstance(node, SineSourceNode)
        assert node.outputs == ("dmx",)

    def test_parse_console_sink_node(self) -> None:
        config = """
        rasl {
            node console {
                type ConsoleSinkNode;
                input universe0;
                max_channels 8;
                as_bytes false;
                every_n 2;
                include_metadata false;
                label "test";
            }
        }
        """
        plan = parse_config(config)

        assert "console" in plan.nodes
        node = plan.nodes["console"]
        assert isinstance(node, ConsoleSinkNode)
        assert node.inputs == ("universe0",)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_from_file(self) -> None:
        """Test loading config from a file."""
        config = """
        rasl {
            node source {
                type SacnSourceNode;
                universes 1;
            }
        }
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config)
            temp_path = Path(f.name)

        try:
            plan = load_config(temp_path)
            assert len(plan.nodes) == 1
        finally:
            temp_path.unlink()

    def test_load_nonexistent_file_raises(self) -> None:
        """Test that loading nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.conf")

    def test_load_accepts_string_path(self) -> None:
        """Test that load_config accepts string path."""
        config = """
        rasl {
            node source {
                type SacnSourceNode;
                universes 1;
            }
        }
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config)
            temp_path = f.name

        try:
            plan = load_config(temp_path)  # String path
            assert len(plan.nodes) == 1
        finally:
            Path(temp_path).unlink()
