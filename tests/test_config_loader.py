"""Unit tests for the configuration loader."""

import pytest

from rasl.config.loader import ConfigError, parse_config
from rasl.engine.registry import reset_registries


@pytest.fixture(autouse=True)
def setup_nodes():
    """Ensure nodes are registered before tests."""
    # Import nodes to trigger registration (don't reset registry)
    from rasl.engine.registry import ensure_nodes_loaded
    import rasl.nodes  # noqa: F401
    ensure_nodes_loaded()
    yield


class TestParseConfig:
    """Tests for parse_config function."""

    def test_parse_simple_sine_source(self):
        """Test parsing a simple SineSource node."""
        config = """
        rasl {
            node SineSource sine {
                output_channels 512;
                frequency_hz 2.0;
                fps 30;
            }
        }
        """
        plan = parse_config(config)

        assert len(plan.nodes) == 1
        assert "sine" in plan.nodes
        node = plan.nodes["sine"]
        assert node.id == "sine"
        assert node._channels == 512
        assert node._frequency_hz == 2.0
        assert node._fps == 30

    def test_parse_sine_source_with_defaults(self):
        """Test that SineSource uses default values."""
        config = """
        rasl {
            node SineSource sine {
            }
        }
        """
        plan = parse_config(config)
        node = plan.nodes["sine"]
        assert node._channels == 512  # default
        assert node._frequency_hz == 1.0  # default
        assert node._amplitude == 0.5  # default
        assert node._offset == 0.5  # default

    def test_parse_console_sink(self):
        """Test parsing a ConsoleSink node."""
        config = """
        rasl {
            node ConsoleSink console {
                input_port dmx;
                max_channels 24;
                as_bytes true;
            }
        }
        """
        plan = parse_config(config)

        assert "console" in plan.nodes
        node = plan.nodes["console"]
        assert node._input_port == "dmx"
        assert node._max_channels == 24
        assert node._as_bytes is True

    def test_parse_sacn_sink_requires_target_host(self):
        """Test that SacnSink requires target_host."""
        config = """
        rasl {
            node SacnSink sink {
                input_port universe0;
                target_universe 0;
            }
        }
        """
        with pytest.raises(ConfigError, match="target_host"):
            parse_config(config)

    def test_parse_connections(self):
        """Test parsing edge connections (inside node blocks)."""
        config = """
        rasl {
            node SineSource sine {
                output_channels 512;
            }
            node ConsoleSink console {
                input_port dmx;
                connect sine dmx;
            }
        }
        """
        plan = parse_config(config)

        assert len(plan.adjacency["sine"]) == 1
        edge = plan.adjacency["sine"][0]
        assert edge.source == "sine"
        assert edge.source_port == "dmx"
        assert edge.target == "console"
        assert edge.target_port == "dmx"

    def test_parse_unknown_node_type_raises(self):
        """Test that unknown node type raises ConfigError."""
        config = """
        rasl {
            node UnknownType foo {
            }
        }
        """
        with pytest.raises(ConfigError, match="Unknown node type"):
            parse_config(config)

    def test_parse_no_rasl_block_raises(self):
        """Test that missing rasl block raises ConfigError."""
        config = """
        other {
            node SineSource sine {}
        }
        """
        with pytest.raises(ConfigError, match="No 'rasl' block"):
            parse_config(config)

    def test_parse_invalid_config_field_raises(self):
        """Test that invalid config field raises ConfigError."""
        config = """
        rasl {
            node SineSource sine {
                frequency_hz 999;
            }
        }
        """
        # frequency_hz max is 100.0
        with pytest.raises(ConfigError, match="frequency_hz"):
            parse_config(config)

    def test_parse_with_metadata(self):
        """Test parsing node with metadata."""
        config = '''
        rasl {
            node SineSource sine {
                metadata "colorSpace=rgb";
            }
        }
        '''
        plan = parse_config(config)
        node = plan.nodes["sine"]
        assert node._metadata == {"colorSpace": "rgb"}

    def test_parse_legacy_type_syntax(self):
        """Test parsing with legacy 'type' directive syntax."""
        config = """
        rasl {
            node sine {
                type SineSource;
                output_channels 256;
            }
        }
        """
        plan = parse_config(config)
        assert "sine" in plan.nodes
        assert plan.nodes["sine"]._channels == 256

    def test_parse_node_aliases(self):
        """Test that node type aliases work."""
        config = """
        rasl {
            node SineSourceNode sine {
                output_channels 128;
            }
        }
        """
        plan = parse_config(config)
        assert "sine" in plan.nodes


class TestDefaultPorts:
    """Tests for default port resolution in connect blocks."""

    def test_default_input_port(self):
        """Test that single input port is used as default."""
        config = """
        rasl {
            node SineSource sine {}
            node ConsoleSink console {
                input_port dmx;
                connect sine;
            }
        }
        """
        plan = parse_config(config)
        edge = plan.adjacency["sine"][0]
        assert edge.target_port == "dmx"  # ConsoleSink has single input

    def test_nested_connect_uses_current_node_as_target(self):
        """Test that nested connect with single arg targets current node."""
        config = """
        rasl {
            node SineSource sine {}
            node ConsoleSink console {
                input_port dmx;
                connect sine;
            }
        }
        """
        plan = parse_config(config)
        edge = plan.adjacency["sine"][0]
        assert edge.target == "console"
        assert edge.target_port == "dmx"  # ConsoleSink has single input
