from __future__ import annotations

from rasl.engine.node_config import (
    IOHints,
    NodeConfig,
    NodeEngineHints,
    NodeKind,
    PortIOConfig,
    SinkNodeConfig,
    SourceNodeConfig,
    TimingConfig,
    TimingHints,
    TransformNodeConfig,
)


class TestNodeConfigTypes:
    def test_source_node_config_basic(self) -> None:
        timing = TimingConfig(fps=None)
        output = PortIOConfig(channels=512, port="dmx")
        cfg = SourceNodeConfig(
            id="sine1",
            type_id="SineSource",
            kind=NodeKind.SOURCE,
            timing=timing,
            params={},
            output=output,
        )

        assert cfg.id == "sine1"
        assert cfg.type_id == "SineSource"
        assert cfg.kind is NodeKind.SOURCE
        assert cfg.timing.fps is None
        assert cfg.input is None
        assert cfg.output is output
        assert cfg.output.channels == 512
        assert cfg.output.port == "dmx"

    def test_sink_node_config_basic(self) -> None:
        timing = TimingConfig(fps=30.0)
        input_cfg = PortIOConfig(channels=40, port="in")
        cfg = SinkNodeConfig(
            id="console1",
            type_id="ConsoleSink",
            kind=NodeKind.SINK,
            timing=timing,
            params={"every_n": 2},
            input=input_cfg,
        )

        assert cfg.id == "console1"
        assert cfg.type_id == "ConsoleSink"
        assert cfg.kind is NodeKind.SINK
        assert cfg.timing.fps == 30.0
        assert cfg.input is input_cfg
        assert cfg.input.channels == 40
        assert cfg.input.port == "in"
        assert cfg.output is None

    def test_transform_node_config_basic(self) -> None:
        timing = TimingConfig(fps=60.0)
        input_cfg = PortIOConfig(channels=40, port="in")
        output_cfg = PortIOConfig(channels=40, port="out")
        cfg = TransformNodeConfig(
            id="xf",
            type_id="ExampleTransform",
            kind=NodeKind.TRANSFORM,
            timing=timing,
            params={},
            input=input_cfg,
            output=output_cfg,
        )

        assert cfg.kind is NodeKind.TRANSFORM
        assert cfg.input is input_cfg
        assert cfg.output is output_cfg


class TestNodeEngineHints:
    def test_engine_hints_structure(self) -> None:
        timing_hints = TimingHints(default_fps=30.0, min_fps=1.0, max_fps=120.0)
        input_hints = IOHints(default_channels=512, default_port="dmx")
        output_hints = IOHints(default_channels=40, default_port="in")

        hints = NodeEngineHints(
            timing=timing_hints,
            input=input_hints,
            output=output_hints,
        )

        assert hints.timing.default_fps == 30.0
        assert hints.timing.min_fps == 1.0
        assert hints.timing.max_fps == 120.0
        assert hints.input is input_hints
        assert hints.input.default_channels == 512
        assert hints.input.default_port == "dmx"
        assert hints.output is output_hints
        assert hints.output.default_channels == 40
        assert hints.output.default_port == "in"
