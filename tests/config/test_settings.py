"""The top-level ui and runtime blocks."""

from __future__ import annotations

import pytest

from rasl.config import ConfigError, RuntimeSettings, UiSettings, runtime_settings, ui_settings
from rasl.config.build import parse_config
from rasl.config.document import parse_document


class TestUi:
    def test_no_block_means_no_server_from_the_config(self) -> None:
        assert ui_settings(parse_document("graph { }")) == UiSettings()

    def test_host_and_port(self) -> None:
        tree = parse_document("ui { host 0.0.0.0; port 9000; }\ngraph { }")
        assert ui_settings(tree) == UiSettings(enabled=True, host="0.0.0.0", port=9000)

    @pytest.mark.parametrize("port", ['"abc"', "0", "70000", "1 2"])
    def test_a_bad_port_is_a_located_error(self, port: str) -> None:
        tree = parse_document(f"ui {{\n    port {port};\n}}\ngraph {{ }}")
        with pytest.raises(ConfigError, match="'port'") as caught:
            ui_settings(tree)
        assert caught.value.line == 2


class TestRuntime:
    def test_defaults_to_ten(self) -> None:
        assert runtime_settings(parse_document("graph { }")) == RuntimeSettings(10)

    def test_a_limit_and_zero(self) -> None:
        tree = parse_document("runtime { max_consecutive_errors 0; }\ngraph { }")
        assert runtime_settings(tree).max_consecutive_errors == 0

    def test_a_negative_limit_and_an_unknown_setting_are_errors(self) -> None:
        with pytest.raises(ConfigError, match="'max_consecutive_errors' must be a whole number 0 or more"):
            runtime_settings(parse_document("runtime { max_consecutive_errors -1; }\ngraph { }"))
        with pytest.raises(ConfigError, match="Unknown runtime setting 'retries'"):
            runtime_settings(parse_document("runtime { retries 3; }\ngraph { }"))

    def test_debug_frames_is_off_unless_set_true(self) -> None:
        assert runtime_settings(parse_document("graph { }")).debug_frames is False
        tree = parse_document("runtime { debug_frames true; }\ngraph { }")
        assert runtime_settings(tree) == RuntimeSettings(10, debug_frames=True)
        with pytest.raises(ConfigError, match="'debug_frames' must be true or false, got 'yes'"):
            runtime_settings(parse_document("runtime { debug_frames yes; }\ngraph { }"))


def test_a_node_can_set_its_own_limit() -> None:
    plan = parse_config("graph {\n    node ConsoleSink c { fps 1; max_consecutive_errors 3; }\n}\n")
    assert plan.nodes["c"].max_consecutive_errors == 3
