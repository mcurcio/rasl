"""The config document layer: directives and values, port references, connect
directives, and one device config read end to end."""


import pytest

from rasl.config.connection import (
    parse_connect_directive,
    parse_port_ref,
)
from rasl.config.document import (
    ConfigError,
    Directive,
    arg_texts,
    children,
    config_error,
    line_of,
    load_document,
    parse_document,
    scalar,
)
from rasl.config.loader import parse_config
from rasl.engine.slices import Slice


def _directive(text: str) -> Directive:
    """The one directive `text` holds."""
    return parse_document(text).block[0]


# ─────────────────────────────────────────────────────────────────────
# Config Document Tests
# ─────────────────────────────────────────────────────────────────────


class TestDocument:
    """Tests for rasl.config.document: loading a config through knobly."""

    def test_parse_document(self):
        """Parse config from string into a tree of directives."""
        tree = parse_document(
            """
        graph {
            node Test foo {
                value 42;
            }
        }
        """
        )

        assert len(tree.block) == 1

        graph = tree.block[0]
        assert graph.name == "graph"

        node = graph.block[0]
        assert node.name == "node"
        assert arg_texts(node) == ("Test", "foo")
        assert line_of(node) == 3

    def test_children(self):
        """children returns the block's directives, all or by name."""
        d = _directive("node { connect a; fps 30; connect b; }")

        assert [c.name for c in children(d)] == ["connect", "fps", "connect"]
        assert [arg_texts(c) for c in children(d, "connect")] == [("a",), ("b",)]
        assert children(d, "nonexistent") == ()
        assert children(_directive("fps 30;")) == ()

    def test_arg_texts(self):
        """Each kind of value is the string rasl's parsers take."""
        d = _directive(
            """x sine 0.5 "10.0.0.1" 'C:\\new' up.rgb[0~3] up[4~] up[~8] up[5] [[1, 0], [0.5,0]];"""
        )

        assert arg_texts(d) == (
            "sine",
            "0.5",
            "10.0.0.1",
            "C:\\new",
            "up.rgb[0:3]",
            "up[4:]",
            "up[:8]",
            "up[5]",
            "[[1, 0], [0.5, 0]]",
        )

    def test_scalar(self):
        """Bare words are coerced; quoted strings stay text; lists are read item by item."""
        d = _directive("""x 42 3.14 on No sine "42" "on" [1, 0.5, off, "a"] up[0~3];""")

        assert [scalar(v) for v in d.values] == [
            42,
            3.14,
            True,
            False,
            "sine",
            "42",
            "on",
            [1, 0.5, False, "a"],
            "up[0:3]",
        ]

    def test_variables_and_snippets(self):
        """@set and @snippet / @use are worked out before rasl reads the tree."""
        tree = parse_document(
            """
        @set $pixels 2284;
        @snippet sink $name {
            node DdpSink $name { max_count $pixels; }
        }
        graph {
            @use sink leds;
            @use sink porch;
        }
        """
        )

        nodes = tree.block[0].block
        assert [arg_texts(n) for n in nodes] == [("DdpSink", "leds"), ("DdpSink", "porch")]
        assert [scalar(n.block[0].values[0]) for n in nodes] == [2284, 2284]

    def test_load_document_with_include(self, tmp_path):
        """A file is loaded with the files it includes, each include with its own variables."""
        (tmp_path / "main.conf").write_text(
            'graph {\n    @include "sink.conf" { @set $name leds; }\n}\n'
        )
        (tmp_path / "sink.conf").write_text("node DdpSink $name;\n")

        tree = load_document(tmp_path / "main.conf")

        node = tree.block[0].block[0]
        assert arg_texts(node) == ("DdpSink", "leds")
        assert line_of(node) == 1  # where it is written, in sink.conf

    def test_load_document_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_document(tmp_path / "missing.conf")

    def test_syntax_error_raises_located_config_error(self):
        """A problem knobly finds is a ConfigError with the place and the source line."""
        with pytest.raises(ConfigError) as exc_info:
            parse_document("graph {\n    fps 30\n}\n")

        error = exc_info.value
        assert error.line == 3
        assert error.column == 0
        assert [d.code for d in error.diagnostics] == ["E2001"]
        assert str(error) == 'config:3:1: E2001: unexpected token: "}"\n}\n^'

    def test_old_slice_spelling_is_an_error(self):
        """A slice is written with ~; the old [0:3] is refused, not misread."""
        with pytest.raises(ConfigError, match="E2007"):
            parse_document("connect up[0:3];")

    def test_every_problem_is_reported(self):
        with pytest.raises(ConfigError) as exc_info:
            parse_document("a $x;\nb $y;\n")

        assert [(d.code, d.place.span.start.line) for d in exc_info.value.diagnostics] == [
            ("E5001", 0),
            ("E5001", 1),
        ]

    def test_config_error_is_placed_on_a_directive(self):
        tree = parse_document("graph {\n    node Mystery m;\n}\n")
        node = tree.block[0].block[0]

        error = config_error(node, "Unknown node type 'Mystery'", code="rasl/unknown-node", tree=tree)

        assert error.message == "Unknown node type 'Mystery'"
        assert error.line == 2
        assert str(error) == (
            "config:2:5: rasl/unknown-node: Unknown node type 'Mystery'\n"
            "    node Mystery m;\n"
            "    ^^^^"
        )


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
        assert ref.slice_ == Slice(0, 100)

    def test_node_with_open_slice(self):
        """Parse node[start:] syntax (open-ended)."""
        ref = parse_port_ref("upstream[50:]")
        assert ref.node == "upstream"
        assert ref.slice_ == Slice(50, None)

    def test_full_syntax(self):
        """Parse node[start:end].port syntax."""
        ref = parse_port_ref("upstream[0:151].rgb")
        assert ref.node == "upstream"
        assert ref.port == "rgb"
        assert ref.slice_ == Slice(0, 151)

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
        directive = _directive("connect upstream;")
        desc = parse_connect_directive(directive)

        assert desc.source == "upstream"
        assert desc.target is None
        assert desc.repeat == 1

    def test_source_and_target(self):
        """Parse connect with source and target."""
        directive = _directive("connect upstream pixels;")
        desc = parse_connect_directive(directive)

        assert desc.source == "upstream"
        assert desc.target == "pixels"
        assert desc.repeat == 1


class TestDdpSinkConfig:
    def test_ddp_sink_accepts_max_channels(self):
        config = """
        graph {
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
        directive = _directive("connect upstream pixels { repeat 20; }")
        desc = parse_connect_directive(directive)

        assert desc.source == "upstream"
        assert desc.target == "pixels"
        assert desc.repeat == 20

    def test_with_repeat_until(self):
        """Parse connect with repeat_until option."""
        directive = _directive("connect upstream pixels { repeat_until 2284; }")
        desc = parse_connect_directive(directive)

        assert desc.source == "upstream"
        assert desc.target == "pixels"
        assert desc.repeat == 1
        assert desc.repeat_until == 2284

    def test_repeat_and_repeat_until_mutually_exclusive(self):
        """repeat and repeat_until cannot be specified together."""
        directive = _directive("connect upstream pixels { repeat 2; repeat_until 10; }")
        with pytest.raises(ValueError, match="both repeat and repeat_until"):
            parse_connect_directive(directive)

    def test_sliced_source(self):
        """Parse connect with sliced source."""
        directive = _directive("connect upstream[0~100] pixels;")
        desc = parse_connect_directive(directive)

        assert desc.source == "upstream[0:100]"
        assert desc.target == "pixels"

    def test_empty_args_raises(self):
        """Connect with no args raises ValueError."""
        directive = _directive("connect;")
        with pytest.raises(ValueError, match="requires at least one argument"):
            parse_connect_directive(directive)


# ─────────────────────────────────────────────────────────────────────
# Integration Tests
# ─────────────────────────────────────────────────────────────────────
