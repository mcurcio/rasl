"""Unit tests for the configuration loader."""

import pytest
from pydantic import BaseModel, ConfigDict, Field

from rasl.config.build import parse_config
from rasl.config.document import ConfigError
from rasl.graph.node import (
    BaseNode,
    SinkNodeConfig,
    TickContext,
    TransformNodeConfig,
    node,
    pull_rate,
)
from rasl.graph.ports import InputPortSpec, PortGroup
from rasl.signal import MatrixPayload


@pytest.fixture(autouse=True)
def setup_nodes():
    """Ensure nodes are registered before tests."""
    # Import nodes to trigger registration (don't reset registry)
    import rasl.nodes  # noqa: F401
    from rasl.graph.node import ensure_nodes_loaded
    ensure_nodes_loaded()
    yield


class TestParseConfig:
    """Tests for parse_config function."""

    def test_parse_simple_sine_source(self):
        """Test parsing a simple SineSource node."""
        config = """
        graph {
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
        graph {
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
        graph {
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
        graph {
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
        graph {
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
        graph {
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
        with pytest.raises(ConfigError, match="No 'graph' block"):
            parse_config(config)

    def test_errors_are_placed_in_the_config(self):
        """A loader error names the place and shows the source line."""
        config = "graph {\n    node NonExistentNode test {}\n}\n"
        with pytest.raises(ConfigError) as exc_info:
            parse_config(config)

        error = exc_info.value
        assert error.message == "Unknown node type 'NonExistentNode'"
        assert error.line == 2
        assert str(error) == (
            "config:2:5: rasl/unknown-node: Unknown node type 'NonExistentNode'\n"
            "    node NonExistentNode test {}\n"
            "    ^^^^"
        )

    def test_invalid_field_is_placed_on_its_directive(self):
        config = "graph {\n    node SineSource sine {\n        fps 30;\n        output_channels many;\n    }\n}\n"
        with pytest.raises(ConfigError, match="Invalid config for node 'sine'") as exc_info:
            parse_config(config)

        assert exc_info.value.line == 4
        assert [d.code for d in exc_info.value.diagnostics] == ["rasl/invalid-node"]

    def test_parse_invalid_config_field_raises(self):
        """Test that invalid config field raises ConfigError."""
        config = """
        graph {
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
        graph {
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
        graph {
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
        graph {
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
        graph {
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
        graph {
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


class TestValuesAfterTheNodeName:
    """Values on a node's own line belong to the node type (Config.from_positional)."""

    def test_a_node_type_that_takes_none_refuses_them(self):
        with pytest.raises(ConfigError, match="this node type takes no values after its name") as caught:
            parse_config("graph {\n    node Smooth soft extra { }\n}\n")
        assert caught.value.line == 2

    def test_color_takes_its_model(self):
        plan = parse_config("graph {\n    node Color c oklch { }\n}\n")
        assert plan.nodes["c"]._model == "oklch"

    def test_color_refuses_a_second_value(self):
        with pytest.raises(ConfigError, match="a Color node takes one value after its name"):
            parse_config("graph {\n    node Color c oklch extra { }\n}\n")

    def test_cron_takes_one_to_five_fields(self):
        parse_config("graph {\n    node cron every * * * * *;\n}\n")
        with pytest.raises(ConfigError, match="cron node supports 1-5 fields, got 6"):
            parse_config("graph {\n    node cron every * * * * * *;\n}\n")
        # With no fields on the line, the schedule comes from the block
        plan = parse_config("graph {\n    node cron every { schedule \"*/5 * * * *\"; }\n}\n")
        assert "every" in plan.nodes


class _Zone(BaseModel):
    """One repeated block of _ZonesNode."""

    model_config = ConfigDict(extra="forbid")
    id: int
    size: int = 1


@node("TestZones")
class _ZonesNode(BaseNode):
    """A node whose ``zone`` blocks fill a list field; never runs."""

    class Config(TransformNodeConfig):
        """Configuration for _ZonesNode."""

        zones: list[_Zone] = Field(default_factory=list, alias="zone")

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.zones = config.zones

    async def pull(self, tick: TickContext) -> None:
        """Do nothing."""


class TestRepeatedBlocks:
    def test_one_block_fills_a_list_field_like_several_do(self):
        one = parse_config("graph {\n    node TestZones s { zone { id 1; size 10; } }\n}\n")
        two = parse_config("graph {\n    node TestZones s { zone { id 1; size 10; } zone { id 2; } }\n}\n")
        assert [(z.id, z.size) for z in one.nodes["s"].zones] == [(1, 10)]
        assert [(z.id, z.size) for z in two.nodes["s"].zones] == [(1, 10), (2, 1)]


class _RateConfig(SinkNodeConfig):
    """A sink whose rate is a setting, as a plugin's might be."""

    hz: float = 1.0


@node("TestSettableRateSink")
class _SettableRateSink(BaseNode):
    """Pulled at its ``hz`` setting, which nothing stops from being 0."""

    Config = _RateConfig
    inputs = PortGroup.inputs(input=InputPortSpec(MatrixPayload))

    def __init__(self, config: _RateConfig) -> None:
        super().__init__(config)
        self._hz = config.hz

    @pull_rate(lambda self: self._hz)
    async def pull(self, tick: TickContext) -> None:
        """Do nothing."""


class TestPullRates:
    @pytest.mark.parametrize("hz", ["0", "-1", "inf"])
    def test_a_bad_rate_from_settings_is_a_located_config_error(self, hz: str) -> None:
        with pytest.raises(ConfigError, match="rasl/rate: Node 'sink' declares a pull rate") as caught:
            parse_config(f"graph {{\n    node TestSettableRateSink sink {{ hz {hz}; }}\n}}\n")
        assert caught.value.line == 2

    def test_a_good_rate_loads(self) -> None:
        parse_config("graph {\n    node TestSettableRateSink sink { hz 30; }\n}\n")


class TestMetadata:
    @staticmethod
    def _md(body: str) -> dict:
        plan = parse_config(f"graph {{\n    node ConsoleSink c {{ fps 1; {body} }}\n}}\n")
        return dict(plan.nodes["c"]._metadata)

    def test_the_block_form(self) -> None:
        assert self._md('metadata { room den; zone "2"; }') == {"room": "den", "zone": "2"}

    def test_the_string_form_still_works(self) -> None:
        assert self._md('metadata "room=den" "zone=2";') == {"room": "den", "zone": "2"}

    def test_both_forms_merge(self) -> None:
        assert self._md('metadata "room=den"; metadata { zone 2; }') == {"room": "den", "zone": "2"}

    @pytest.mark.parametrize(
        ("body", "message"),
        [
            ('metadata "room=den"; metadata { room hall; }', "metadata key 'room' is given twice"),
            ("metadata { room den hall; }", "metadata entry 'room' takes exactly one value"),
            ("metadata { room; }", "metadata entry 'room' takes exactly one value"),
            ("metadata { room { name den; } }", "metadata entry 'room' takes exactly one value"),
            ("metadata x { room den; }", "a metadata block takes no values on its own line"),
        ],
    )
    def test_a_bad_entry_is_a_located_error(self, body: str, message: str) -> None:
        with pytest.raises(ConfigError, match=message) as caught:
            self._md(body)
        assert caught.value.line == 2
