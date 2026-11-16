"""Tests for rasl.config.edit: graph edits written to the config files."""

from __future__ import annotations

from pathlib import Path

import pytest

from rasl.config.build import load_config
from rasl.config.edit import (
    AddNode,
    ConfigEditor,
    Connect,
    Disconnect,
    EditConflict,
    EditRefused,
    RemoveNode,
    RenameNode,
)

BASE = """\
graph {
    # the clock
    node cron minute * * * * *;

    node Waveform hue {
        output_channels 4;
    }

    node ConsoleSink sink {
        fps 1;
        connect minute;  # the tick
    }
}
"""


@pytest.fixture
def config(tmp_path: Path) -> Path:
    path = tmp_path / "rasl.conf"
    path.write_text(BASE)
    return path


def _apply(path: Path, *edits):
    editor = ConfigEditor(path)
    return editor.apply(list(edits), base_version=editor.version())


class TestAddNode:
    def test_a_node_without_connections_goes_at_the_end_of_the_graph_block(self, config: Path) -> None:
        result = _apply(config, AddNode("ConsoleSink", "debug", settings=(("fps", "2"),)))
        assert result.ok, result.error
        assert config.read_text() == BASE.replace(
            "        connect minute;  # the tick\n    }\n}\n",
            "        connect minute;  # the tick\n    }\n"
            "    node ConsoleSink debug {\n        fps 2;\n    }\n}\n",
        )
        load_config(config)

    def test_a_node_fed_by_another_goes_right_after_it(self, config: Path) -> None:
        result = _apply(
            config,
            AddNode("ConsoleSink", "debug", settings=(("fps", "2"),)),
            Connect("minute", "debug"),
        )
        assert result.ok, result.error
        text = config.read_text()
        assert "    node cron minute * * * * *;\n\n    node ConsoleSink debug {\n        fps 2;\n" in text
        assert "        connect minute;\n    }\n" in text
        plan = load_config(config)
        assert ("minute", "out", "debug", "dmx") in plan.describe()["edges"]

    def test_a_node_feeding_another_goes_right_before_it(self, config: Path) -> None:
        result = _apply(
            config,
            Disconnect("minute", "sink"),
            AddNode("cron", "hour", values="0 * * * *"),
            Connect("hour", "sink"),
        )
        assert result.ok, result.error
        text = config.read_text()
        assert text.index("node cron hour 0 * * * *;") < text.index("node ConsoleSink sink")
        assert text.index("node cron hour") > text.index("node Waveform hue")

    def test_a_taken_id_is_refused(self, config: Path) -> None:
        with pytest.raises(EditRefused, match="A node 'hue' already exists"):
            _apply(config, AddNode("Waveform", "hue"))
        assert config.read_text() == BASE

    def test_a_malformed_id_is_refused(self, config: Path) -> None:
        with pytest.raises(EditRefused, match="'2x' is not a node id"):
            _apply(config, AddNode("Waveform", "2x"))


class TestConnect:
    def test_a_connection_goes_in_the_receiving_nodes_block(self, config: Path) -> None:
        result = _apply(config, AddNode("ConsoleSink", "debug", settings=(("fps", "1"),)), Connect("hue[0~2]", "debug"))
        assert result.ok, result.error
        assert "        fps 1;\n        connect hue[0~2];\n    }" in config.read_text()

    def test_a_node_written_without_a_block_gets_one(self, config: Path) -> None:
        # cron takes no input, so the dry build refuses; the text is still shown
        editor = ConfigEditor(config)
        result = editor.preview([Connect("hue", "minute")], base_version=editor.version())
        after = result.changes[0].after
        assert "    # the clock\n    node cron minute * * * * * {\n        connect hue;\n    }\n" in after
        assert not result.ok and result.error is not None
        assert config.read_text() == BASE

    def test_repeat_is_written_in_the_connections_block(self, config: Path) -> None:
        editor = ConfigEditor(config)
        result = editor.preview(
            [AddNode("ConsoleSink", "debug", settings=(("fps", "1"),)), Connect("minute", "debug", repeat=3)],
            base_version=editor.version(),
        )
        assert "        connect minute {\n            repeat 3;\n        }\n" in result.changes[0].after

    def test_a_second_identical_connection_is_not_saved(self, config: Path) -> None:
        result = _apply(config, Connect("minute", "sink"))
        assert not result.ok
        assert "Duplicate connection" in str(result.error)
        assert config.read_text() == BASE


class TestDisconnect:
    def test_the_line_and_its_comment_go(self, config: Path) -> None:
        result = _apply(config, Disconnect("minute", "sink"))
        assert result.ok, result.error
        assert "connect" not in config.read_text()
        assert "# the tick" not in config.read_text()

    def test_an_unknown_line_is_refused(self, config: Path) -> None:
        with pytest.raises(EditRefused, match="Node 'sink' has no line 'connect hue'"):
            _apply(config, Disconnect("hue", "sink"))


class TestRemoveNode:
    def test_the_connections_that_read_it_go_with_it(self, config: Path) -> None:
        result = _apply(config, RemoveNode("minute"))
        assert result.ok, result.error
        text = config.read_text()
        assert "minute" not in text
        assert "# the clock" not in text
        assert "node ConsoleSink sink {\n        fps 1;\n    }" in text

    def test_an_unknown_node_is_refused(self, config: Path) -> None:
        with pytest.raises(EditRefused, match="No node 'nope' in the graph"):
            _apply(config, RemoveNode("nope"))


class TestRenameNode:
    def test_the_id_and_every_reader_change(self, config: Path) -> None:
        result = _apply(config, RenameNode("minute", "tick"))
        assert result.ok, result.error
        text = config.read_text()
        assert "node cron tick * * * * *;" in text
        assert "connect tick;  # the tick" in text
        assert "minute" not in text


class TestLocked:
    def test_a_node_from_a_snippet_is_locked(self, tmp_path: Path) -> None:
        path = tmp_path / "rasl.conf"
        path.write_text(
            "@snippet clock $name {\n    node cron $name * * * * *;\n}\n"
            "graph {\n    @use clock minute;\n}\n"
        )
        with pytest.raises(EditRefused, match="written in @snippet clock; it is locked"):
            _apply(path, RemoveNode("minute"))


class TestVersions:
    def test_an_edit_against_an_old_version_is_a_conflict(self, config: Path) -> None:
        editor = ConfigEditor(config)
        version = editor.version()
        config.write_text(BASE.replace("fps 1", "fps 2"))
        with pytest.raises(EditConflict):
            editor.apply([RemoveNode("hue")], base_version=version)

    def test_a_preview_writes_nothing_and_shows_the_diff(self, config: Path) -> None:
        editor = ConfigEditor(config)
        result = editor.preview([RemoveNode("hue")], base_version=editor.version())
        assert result.ok
        assert "-    node Waveform hue {" in result.diff
        assert config.read_text() == BASE

    def test_a_saved_batch_returns_the_new_version(self, config: Path) -> None:
        editor = ConfigEditor(config)
        result = editor.apply([RemoveNode("hue")], base_version=editor.version())
        assert result.saved == (str(config),)
        assert result.version == editor.version()


def test_a_trailing_comment_moves_after_the_new_block(tmp_path: Path) -> None:
    path = tmp_path / "rasl.conf"
    path.write_text(
        "graph {\n    node Waveform hue { output_channels 4; }\n"
        "    node ConsoleSink sink fps; # note; not code\n}\n"
    )
    editor = ConfigEditor(path)
    result = editor.preview([Connect("hue", "sink")], base_version=editor.version())
    assert "    node ConsoleSink sink fps {\n        connect hue;\n    } # note; not code\n" in result.changes[0].after
