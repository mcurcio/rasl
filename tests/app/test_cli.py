"""The rasl command: what it prints, and where."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import structlog

from rasl.app.cli import main

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def restore_logging():
    """Put back the logging setup main() changes, so later tests do not log to a closed stream."""
    saved = structlog.get_config()
    yield
    structlog.configure(**saved)


class TestDescribe:
    def test_stdout_is_only_the_json_description(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["--describe", str(REPO / "virtual.conf")]) == 0
        out, err = capsys.readouterr()
        description = json.loads(out)  # nothing but JSON on stdout
        assert description["nodes"]
        assert "config_loaded" in err  # the log lines go to stderr


class TestValidate:
    def test_a_bad_ui_port_is_a_config_error_not_a_crash(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = tmp_path / "bad.conf"
        config.write_text('ui {\n    port "abc";\n}\ngraph { }\n')
        assert main(["--validate", str(config)]) == 1
        assert "bad.conf:2:5" in capsys.readouterr().err

    def test_a_good_config_is_reported_valid(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = tmp_path / "good.conf"
        config.write_text("graph {\n    node cron minute;\n    node ConsoleSink sink { fps 1; connect minute; }\n}\n")
        assert main(["--validate", str(config)]) == 0
        out, err = capsys.readouterr()
        assert "Config valid: 2 nodes" in out
        assert "Warning" not in err

    def test_nodes_that_nothing_pulls_are_named_in_a_warning(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = tmp_path / "undriven.conf"
        config.write_text("graph {\n    node cron lonely;\n}\n")
        assert main(["--validate", str(config)]) == 0  # it loads: the nodes just never run
        assert "never run" in capsys.readouterr().err

    def test_an_unknown_node_type_is_an_error(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = tmp_path / "bad.conf"
        config.write_text("graph {\n    node NoSuchNode x;\n}\n")
        assert main(["--validate", str(config)]) == 1
        assert "Error loading config" in capsys.readouterr().err


class TestArguments:
    def test_no_config_prints_the_help_and_fails(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main([]) == 1
        assert "usage: rasl" in capsys.readouterr().out

    def test_a_missing_config_file_fails(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main([str(tmp_path / "nothing.conf")]) == 1
        assert "Config file not found" in capsys.readouterr().err

    def test_version_prints_and_exits_0(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(["--version"])
        assert exit_info.value.code == 0
        assert capsys.readouterr().out.startswith("rasl ")
