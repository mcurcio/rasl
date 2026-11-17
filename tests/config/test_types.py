"""Connection types are checked at load: kinds and pass-through outputs."""

from __future__ import annotations

import pytest

from rasl.color import ColorPayload
from rasl.config.build import parse_config
from rasl.config.document import ConfigError
from rasl.graph.node import get_outputs
from rasl.signal import BoolPayload, MatrixPayload

WAVE = "node Waveform wave { output_channels 3; fps 10; }"
COLOR = "node Color rgb srgb { connect wave; }"
LIFX = 'node LifxSink bulbs {{ target "192.168.1.60"; fps 10; connect {source}; }}'


def _graph(*nodes: str) -> str:
    return "graph {\n" + "\n".join(f"    {n}" for n in nodes) + "\n}\n"


class TestKinds:
    def test_a_plain_matrix_does_not_feed_a_generic_color_input(self) -> None:
        # The generic ColorPayload has no model to give bare data: nothing coerces into it
        with pytest.raises(ConfigError, match="wave.out emits MatrixPayload, but bulbs.color does not accept it"):
            parse_config(_graph(WAVE, LIFX.format(source="wave")))

    def test_any_color_model_feeds_a_color_input(self) -> None:
        # Nodes convert colors on arrival, so the model does not have to match
        parse_config(_graph(WAVE, "node Color hsl hsl { connect wave; }", LIFX.format(source="hsl")))

    def test_a_plain_matrix_feeds_a_bool_input_retyped(self) -> None:
        # Owner, 2026-11-16: a general type coerces to a more specific one implicitly
        config = _graph(
            WAVE,
            COLOR,
            "node Crossfade fade { connect rgb input0; connect rgb input1; connect wave[0~1] selector; }",
        )
        plan = parse_config(config)
        assert plan.input_programs[("fade", "selector")].buffer_type is BoolPayload

    def test_a_typed_literal_and_compose_declare_their_type(self) -> None:
        plan = parse_config(
            _graph(
                "node literal warm color:srgb [[1, 0.6, 0.2]];",
                "node Compose hsl { ports { h; s; l; } output_type color:hsl; "
                "fill h 0; fill s 1; fill l 0.5; }",
                LIFX.format(source="warm"),
            )
        )
        # A color literal is a ColorPayload that carries its model
        assert issubclass(get_outputs(plan.nodes["warm"]).get("out").spec.resolve_payload_types()[0], ColorPayload)
        assert get_outputs(plan.nodes["hsl"]).get("out").spec.resolve_payload_types()[0].__name__ == "HslColorPayload"


class TestPassThrough:
    def test_color_through_a_pass_through_node_feeds_a_color_input(self) -> None:
        parse_config(_graph(WAVE, COLOR, "node Smooth calm { connect rgb input; }", LIFX.format(source="calm")))

    def test_a_plain_matrix_through_it_is_an_error_on_the_node_it_feeds(self) -> None:
        config = _graph(WAVE, "node Smooth calm { connect wave input; }", LIFX.format(source="calm"))
        with pytest.raises(
            ConfigError,
            match="Node 'bulbs': Type mismatch: calm.output passes on MatrixPayload from its 'input' input",
        ) as caught:
            parse_config(config)
        assert caught.value.line == 4

    def test_types_follow_a_chain_of_pass_through_nodes(self) -> None:
        parse_config(
            _graph(
                WAVE,
                COLOR,
                "node Smooth calm { connect rgb input; }",
                "node RangeMap squash { ranges [0, 1] [0, 1] [0, 1]; connect calm; }",
                LIFX.format(source="squash"),
            )
        )

    def test_with_nothing_feeding_it_a_pass_through_output_has_its_declared_type(self) -> None:
        plan = parse_config(_graph(WAVE, "node Smooth calm { connect wave input; }"))
        spec = get_outputs(plan.nodes["calm"]).get("output").spec
        assert spec.same_as == "input"
        assert spec.resolve_payload_types()[0] is MatrixPayload
        assert issubclass(BoolPayload, MatrixPayload)
