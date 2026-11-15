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
