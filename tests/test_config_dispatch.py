"""Tests for the new config dispatch system.

Tests cover:
- Directive parsing and manipulation
- ConfigDispatch routing and field parsing
- @config decorator registration
- Connection parsing and expansion
"""

from typing import ClassVar

import pytest
from pydantic import BaseModel

from rasl.config.directive import Directive
from rasl.config.dispatch import ConfigDispatch, ConfigError, config as config_handler
from rasl.config.loader import parse_config
from rasl.config.connection import (
    ConnectionDescriptor,
    ConnectionSpec,
    PortRef,
    parse_connect_directive,
    parse_port_ref,
)
from rasl.config.connect_parser import ResolvedSlice


# ─────────────────────────────────────────────────────────────────────
# Directive Tests
# ─────────────────────────────────────────────────────────────────────


class TestDirective:
    """Tests for Directive class."""

    def test_from_crossplane_simple(self):
        """Parse simple directive without block."""
        raw = {"directive": "fps", "args": ["30"], "line": 5}
        d = Directive.from_crossplane(raw)

        assert d.keyword == "fps"
        assert d.args == ("30",)
        assert d.block == ()
        assert d.line == 5

    def test_from_crossplane_with_block(self):
        """Parse directive with nested block."""
        raw = {
            "directive": "node",
            "args": ["DdpSink", "leds"],
            "block": [
                {"directive": "target", "args": ["10.0.0.1"]},
                {"directive": "fps", "args": ["20"]},
            ],
            "line": 1,
        }
        d = Directive.from_crossplane(raw)

        assert d.keyword == "node"
        assert d.args == ("DdpSink", "leds")
        assert len(d.block) == 2
        assert d.block[0].keyword == "target"
        assert d.block[1].keyword == "fps"

    def test_slice_args(self):
        """slice_args creates new directive with sliced args."""
        d = Directive("node", ("DdpSink", "leds", "rgb"), (), 1)

        sliced = d.slice_args(2)
        assert sliced.args == ("rgb",)
        assert sliced.keyword == "node"
        assert sliced.line == 1

        sliced2 = d.slice_args(1, 2)
        assert sliced2.args == ("leds",)

    def test_with_args(self):
        """with_args creates new directive with replaced args."""
        d = Directive("node", ("old",), (), 1)
        new = d.with_args("new1", "new2")

        assert new.args == ("new1", "new2")
        assert new.keyword == "node"

    def test_find(self):
        """find returns all matching child directives."""
        d = Directive(
            "node",
            (),
            (
                Directive("connect", ("a",), (), 0),
                Directive("fps", ("30",), (), 0),
                Directive("connect", ("b",), (), 0),
            ),
            0,
        )

        connects = d.find("connect")
        assert len(connects) == 2
        assert connects[0].args == ("a",)
        assert connects[1].args == ("b",)

    def test_find_one(self):
        """find_one returns first matching directive."""
        d = Directive(
            "node",
            (),
            (
                Directive("fps", ("30",), (), 0),
                Directive("target", ("10.0.0.1",), (), 0),
            ),
            0,
        )

        fps = d.find_one("fps")
        assert fps is not None
        assert fps.args == ("30",)

        missing = d.find_one("nonexistent")
        assert missing is None

    def test_from_string(self):
        """Parse config from string."""
        content = """
        graph {
            node Test foo {
                value 42;
            }
        }
        """
        root = Directive.from_string(content)

        assert root.keyword == "_root"
        assert len(root.block) == 1

        graph = root.block[0]
        assert graph.keyword == "graph"

        node = graph.block[0]
        assert node.keyword == "node"
        assert node.args == ("Test", "foo")


# ─────────────────────────────────────────────────────────────────────
# ConfigDispatch Tests
# ─────────────────────────────────────────────────────────────────────


class SimpleConfig(BaseModel):
    """Simple config for testing."""

    name: str = "default"
    value: int = 0
    rate: float = 1.0


class ConfigWithArgFields(BaseModel):
    """Config with arg_fields for positional arg mapping."""

    input_port: str = "in"
    output_port: str = "out"

    arg_fields: ClassVar[list[str]] = ["input_port", "output_port"]


class NestedConfig(BaseModel):
    """Config with nested model."""

    name: str


class ParentConfig(BaseModel):
    """Config containing nested config."""

    child: NestedConfig | None = None


class TestConfigDispatch:
    """Tests for ConfigDispatch class."""

    def test_parse_simple_fields(self):
        """Parse simple fields into Pydantic model."""

        class Owner:
            pass

        owner = Owner()
        dispatch = ConfigDispatch(owner)

        directive = Directive(
            "test",
            (),
            (
                Directive("name", ("myname",), (), 0),
                Directive("value", ("42",), (), 0),
                Directive("rate", ("3.14",), (), 0),
            ),
            0,
        )

        config, results = dispatch.process(directive, SimpleConfig)

        assert config.name == "myname"
        assert config.value == 42
        assert config.rate == 3.14
        assert results == {}

    def test_arg_fields_extraction(self):
        """Extract positional args into fields via arg_fields."""

        class Owner:
            pass

        owner = Owner()
        dispatch = ConfigDispatch(owner)

        directive = Directive("test", ("custom_in", "custom_out"), (), 0)

        config, results = dispatch.process(directive, ConfigWithArgFields)

        assert config.input_port == "custom_in"
        assert config.output_port == "custom_out"

    def test_config_handler_called(self):
        """@config decorated methods are called for matching keywords."""
        calls = []

        class Owner:
            @config_handler("custom")
            def handle_custom(self, directive: Directive):
                calls.append(directive.args)
                return f"handled:{directive.args[0]}"

        owner = Owner()
        dispatch = ConfigDispatch(owner)

        directive = Directive(
            "test",
            (),
            (
                Directive("name", ("foo",), (), 0),
                Directive("custom", ("bar",), (), 0),
                Directive("custom", ("baz",), (), 0),
            ),
            0,
        )

        config, results = dispatch.process(directive, SimpleConfig)

        assert config.name == "foo"
        assert len(calls) == 2
        assert ("bar",) in calls
        assert ("baz",) in calls
        assert results["custom"] == ["handled:bar", "handled:baz"]

    def test_config_handler_with_model(self):
        """@config with model pre-parses directive.config."""

        class Options(BaseModel):
            repeat: int = 1

        received_config = []

        class Owner:
            @config_handler("connect", model=Options)
            def handle_connect(self, directive: Directive):
                received_config.append(directive.config)
                return directive.config.repeat

        owner = Owner()
        dispatch = ConfigDispatch(owner)

        directive = Directive(
            "test",
            (),
            (
                Directive(
                    "connect",
                    ("source", "target"),
                    (Directive("repeat", ("5",), (), 0),),
                    0,
                ),
            ),
            0,
        )

        config, results = dispatch.process(directive, SimpleConfig)

        assert len(received_config) == 1
        assert received_config[0].repeat == 5
        assert results["connect"] == [5]

    def test_handler_returns_list(self):
        """Handler returning list extends results."""

        class Owner:
            @config_handler("multi")
            def handle_multi(self, directive: Directive):
                return ["a", "b", "c"]

        owner = Owner()
        dispatch = ConfigDispatch(owner)

        directive = Directive(
            "test",
            (),
            (Directive("multi", (), (), 0),),
            0,
        )

        config, results = dispatch.process(directive, SimpleConfig)

        assert results["multi"] == ["a", "b", "c"]

    def test_unknown_keyword_raises(self):
        """Unknown keyword raises ConfigError."""

        class Owner:
            pass

        owner = Owner()
        dispatch = ConfigDispatch(owner)

        directive = Directive(
            "test",
            (),
            (Directive("unknown", (), (), 5),),
            0,
        )

        with pytest.raises(ConfigError) as exc_info:
            dispatch.process(directive, SimpleConfig)

        assert "unknown" in str(exc_info.value).lower()
        assert exc_info.value.line == 5

    def test_parse_model_simple(self):
        """parse_model parses fields without handlers."""

        class Owner:
            pass

        owner = Owner()
        dispatch = ConfigDispatch(owner)

        class RepeatOptions(BaseModel):
            repeat: int = 1

        directive = Directive(
            "options",
            (),
            (Directive("repeat", ("10",), (), 0),),
            0,
        )

        options = dispatch.parse_model(directive, RepeatOptions)

        assert options.repeat == 10

    def test_bool_coercion(self):
        """Boolean values are coerced correctly."""

        class BoolConfig(BaseModel):
            enabled: bool = False

        class Owner:
            pass

        owner = Owner()
        dispatch = ConfigDispatch(owner)

        for true_val in ["true", "True", "yes", "1", "on"]:
            directive = Directive(
                "test",
                (),
                (Directive("enabled", (true_val,), (), 0),),
                0,
            )
            config, _ = dispatch.process(directive, BoolConfig)
            assert config.enabled is True, f"Failed for {true_val}"

        for false_val in ["false", "False", "no", "0", "off"]:
            directive = Directive(
                "test",
                (),
                (Directive("enabled", (false_val,), (), 0),),
                0,
            )
            config, _ = dispatch.process(directive, BoolConfig)
            assert config.enabled is False, f"Failed for {false_val}"


# ─────────────────────────────────────────────────────────────────────
# Connection Parsing Tests
# ─────────────────────────────────────────────────────────────────────


class TestParsePortRef:
    """Tests for parse_port_ref function."""

    def test_node_only(self):
        """Parse node name only."""
        ref = parse_port_ref("upstream")
        assert ref.node == "upstream"
        assert ref.port is None
        assert ref.slice_ is None

    def test_node_with_port(self):
        """Parse node.port syntax."""
        ref = parse_port_ref("upstream.rgb")
        assert ref.node == "upstream"
        assert ref.port == "rgb"
        assert ref.slice_ is None

    def test_node_with_slice(self):
        """Parse node[start:end] syntax."""
        ref = parse_port_ref("upstream[0:100]")
        assert ref.node == "upstream"
        assert ref.port is None
        assert ref.slice_ == ResolvedSlice(0, 100)

    def test_node_with_open_slice(self):
        """Parse node[start:] syntax (open-ended)."""
        ref = parse_port_ref("upstream[50:]")
        assert ref.node == "upstream"
        assert ref.slice_ == ResolvedSlice(50, None)

    def test_full_syntax(self):
        """Parse node[start:end].port syntax."""
        ref = parse_port_ref("upstream[0:151].rgb")
        assert ref.node == "upstream"
        assert ref.port == "rgb"
        assert ref.slice_ == ResolvedSlice(0, 151)

    def test_empty_string(self):
        """Empty string returns empty PortRef."""
        ref = parse_port_ref("")
        assert ref.node is None
        assert ref.port is None
        assert ref.slice_ is None


class TestParseConnectDirective:
    """Tests for parse_connect_directive function."""

    def test_single_source(self):
        """Parse connect with just source."""
        directive = Directive("connect", ("upstream",), (), 0)
        desc = parse_connect_directive(directive)

        assert desc.source == "upstream"
        assert desc.target is None
        assert desc.repeat == 1

    def test_source_and_target(self):
        """Parse connect with source and target."""
        directive = Directive("connect", ("upstream", "pixels"), (), 0)
        desc = parse_connect_directive(directive)

        assert desc.source == "upstream"
        assert desc.target == "pixels"
        assert desc.repeat == 1


class TestDdpSinkConfig:
    def test_ddp_sink_accepts_max_channels(self):
        config = """
        rasl {
            node literal src matrix [[1,2,3]];
            node DdpSink leds {
                target "10.0.0.1";
                fps 20hz;
                input_port pixels;
                max_count 2284;
                connect src pixels;
            }
        }
        """
        plan = parse_config(config)
        assert "leds" in plan.nodes

    def test_with_repeat(self):
        """Parse connect with repeat option."""
        directive = Directive(
            "connect",
            ("upstream", "pixels"),
            (Directive("repeat", ("20",), (), 0),),
            0,
        )
        desc = parse_connect_directive(directive)

        assert desc.source == "upstream"
        assert desc.target == "pixels"
        assert desc.repeat == 20

    def test_with_repeat_until(self):
        """Parse connect with repeat_until option."""
        directive = Directive(
            "connect",
            ("upstream", "pixels"),
            (Directive("repeat_until", ("2284",), (), 0),),
            0,
        )
        desc = parse_connect_directive(directive)

        assert desc.source == "upstream"
        assert desc.target == "pixels"
        assert desc.repeat == 1
        assert desc.repeat_until == 2284

    def test_repeat_and_repeat_until_mutually_exclusive(self):
        """repeat and repeat_until cannot be specified together."""
        directive = Directive(
            "connect",
            ("upstream", "pixels"),
            (
                Directive("repeat", ("2",), (), 0),
                Directive("repeat_until", ("10",), (), 0),
            ),
            0,
        )
        with pytest.raises(ValueError, match="both repeat and repeat_until"):
            parse_connect_directive(directive)

    def test_sliced_source(self):
        """Parse connect with sliced source."""
        directive = Directive("connect", ("upstream[0:100]", "pixels"), (), 0)
        desc = parse_connect_directive(directive)

        assert desc.source == "upstream[0:100]"
        assert desc.target == "pixels"

    def test_empty_args_raises(self):
        """Connect with no args raises ValueError."""
        directive = Directive("connect", (), (), 0)
        with pytest.raises(ValueError, match="requires at least one argument"):
            parse_connect_directive(directive)


# ─────────────────────────────────────────────────────────────────────
# Integration Tests
# ─────────────────────────────────────────────────────────────────────


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_node_with_connect_handler(self):
        """Simulate node parsing with connect handler returning descriptors."""

        class NodeConfig(BaseModel):
            target: str
            fps: float = 30.0

        class MockNode:
            def __init__(self):
                self.dispatch = ConfigDispatch(self)
                self.descriptors: list[ConnectionDescriptor] = []

            @config_handler("connect")
            def handle_connect(self, directive: Directive) -> ConnectionDescriptor:
                # Parse connect directive into descriptor
                return parse_connect_directive(directive)

        node = MockNode()

        directive = Directive(
            "node",
            (),
            (
                Directive("target", ("10.0.0.1",), (), 0),
                Directive("fps", ("20",), (), 0),
                Directive(
                    "connect",
                    ("wave[0:100]", "pixels[0:]"),
                    (Directive("repeat", ("3",), (), 0),),
                    0,
                ),
            ),
            0,
        )

        config, results = node.dispatch.process(directive, NodeConfig)

        assert config.target == "10.0.0.1"
        assert config.fps == 20.0

        descriptors = results.get("connect", [])
        assert len(descriptors) == 1

        # Verify descriptor captures raw info
        desc = descriptors[0]
        assert desc.source == "wave[0:100]"
        assert desc.target == "pixels[0:]"
        assert desc.repeat == 3
