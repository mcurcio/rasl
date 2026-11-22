"""Element counts fixed when the plan is built (owner, 2026-11-21, rasl-00l)."""

from __future__ import annotations

import pytest

from rasl.config import ConfigError
from rasl.config.build import parse_config
from rasl.graph import GraphBuilder, InputSize, Slice
from rasl.graph.node import NodeContext
from rasl.graph.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.signal import MatrixPayload


def _plan(body: str):
    return parse_config("graph {\n" + body + "\n}\n")


def _error(body: str) -> ConfigError:
    with pytest.raises(ConfigError) as caught:
        _plan(body)
    return caught.value


class TestCountsFromConfigAndInputs:
    def test_sources_take_their_count_from_config(self) -> None:
        plan = _plan(
            """
            node Waveform w { output_channels 7; }
            node SeededRandom r { output_channels 5; }
            node literal l matrix [[0.1], [0.2], [0.3]];
            node ConsoleSink s1 { fps 1; connect w; }
            node ConsoleSink s2 { fps 1; connect r; }
            node ConsoleSink s3 { fps 1; connect l; }
            """
        )
        assert plan.output_counts[("w", "out")] == 7
        assert plan.output_counts[("r", "out")] == 5
        assert plan.output_counts[("l", "out")] == 3
        assert plan.input_counts[("s1", "dmx")] == 7

    def test_a_count_follows_through_same_as_and_count_of(self) -> None:
        plan = _plan(
            """
            node Waveform w { output_channels 9; }
            node Smooth smooth { smooth_period 50ms; connect w input; }
            node Color rgb rgb { connect smooth; }
            node ColorCorrection cc { connect rgb; }
            node ConsoleSink s { fps 1; connect cc; }
            """
        )
        assert plan.output_counts[("smooth", "output")] == 9
        assert plan.output_counts[("rgb", "color")] == 3  # nine values regrouped into RGB
        assert plan.output_counts[("cc", "out")] == 3

    def test_slices_and_repeats_size_the_input(self) -> None:
        plan = _plan(
            """
            node Waveform w { output_channels 4; }
            node ConsoleSink s {
                fps 1;
                connect w[1~3] dmx[0~2];
                connect w dmx[10~];
            }
            node ConsoleSink r { fps 1; connect w { repeat 5; } }
            """
        )
        assert plan.input_counts[("s", "dmx")] == 14
        assert plan.input_counts[("r", "dmx")] == 20

    def test_a_repeat_of_an_open_slice_keeps_its_start(self) -> None:
        # rasl-pd0.11 in the config layer: [2~] of 4 elements is 2 elements from 2
        plan = _plan(
            """
            node Waveform w { output_channels 4; }
            node ConsoleSink s { fps 1; connect w[2~] dmx[0~] { repeat 3; } }
            """
        )
        assert plan.input_counts[("s", "dmx")] == 6
        assert {e.source_slice for e in plan.adjacency["w"]} == {Slice(2, 4)}


class TestNodeRules:
    def test_math_takes_equal_counts_or_one_element_against_many(self) -> None:
        plan = _plan(
            """
            node Waveform a { output_channels 6; }
            node literal one matrix [[0.5]];
            node Math m { operation multiply; connect a a; connect one b; }
            node ConsoleSink s { fps 1; connect m; }
            """
        )
        assert plan.output_counts[("m", "out")] == 6

    def test_math_refuses_other_mismatches_on_the_b_connection(self) -> None:
        error = _error(
            """
            node Waveform a { output_channels 6; }
            node Waveform b { output_channels 4; }
            node Math m {
                connect a a;
                connect b b;
            }
            node ConsoleSink s { fps 1; connect m; }
            """
        )
        assert "Math inputs must have one element count, or one of them 1, got a=6, b=4" in str(error)
        assert error.line == 7

    def test_compose_inputs_share_one_count(self) -> None:
        plan = _plan(
            """
            node Waveform h { output_channels 5; }
            node Compose c { ports { hue; saturation; } output_type array; connect h hue; fill saturation 1; }
            node ConsoleSink s { fps 1; connect c; }
            """
        )
        assert plan.output_counts[("c", "out")] == 5
        error = _error(
            """
            node Waveform h { output_channels 5; }
            node Waveform v { output_channels 3; }
            node Compose c { ports { hue; saturation; } output_type array; connect h hue; connect v saturation; }
            node ConsoleSink s { fps 1; connect c; }
            """
        )
        assert "'saturation' has 3, but 'hue' has 5" in str(error)

    def test_crossfade_inputs_must_match(self) -> None:
        error = _error(
            """
            node literal a color:hsl [[0, 1, 0.5], [0.5, 1, 0.5]];
            node literal b color:hsl [[0, 1, 0.5]];
            node cron sel { schedule "* * * * *"; }
            node Crossfade x { connect a input0; connect b input1; connect sel selector; }
            node ConsoleSink s { fps 1; connect x; }
            """
        )
        assert "Crossfade inputs must have one element count, got input0=2, input1=1" in str(error)


class _Node:
    def __init__(self, node_id: str, out: OutputPortSpec) -> None:
        self.id = node_id
        self.inputs = PortGroup.inputs(**{"in": InputPortSpec(MatrixPayload)})
        self.outputs = PortGroup.outputs(out=out)

    async def start(self, ctx: NodeContext) -> None:
        pass

    async def stop(self, ctx: NodeContext) -> None:
        pass


class TestUnresolved:
    def test_a_source_without_a_count_is_refused_on_its_connection(self) -> None:
        from rasl.graph import PortTypeError

        builder = GraphBuilder()
        builder.add_node(_Node("a", OutputPortSpec(MatrixPayload)))
        builder.add_node(_Node("b", OutputPortSpec(MatrixPayload, count=1)))
        builder.connect("a", "out", "b", "in")
        with pytest.raises(PortTypeError, match=r"Element count unknown: a\.out") as caught:
            builder.build()
        assert caught.value.edge.source == "a"

    def test_an_unconnected_port_needs_no_count(self) -> None:
        builder = GraphBuilder()
        builder.add_node(_Node("a", OutputPortSpec(MatrixPayload)))
        builder.build()

    def test_a_cycle_closed_by_a_counted_back_edge_resolves(self) -> None:
        import warnings

        builder = GraphBuilder()
        builder.add_node(_Node("a", OutputPortSpec(MatrixPayload, same_as="in")))
        builder.add_node(_Node("b", OutputPortSpec(MatrixPayload, count=3)))
        builder.connect("a", "out", "b", "in")
        builder.connect("b", "out", "a", "in")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            plan = builder.build()
        assert plan.output_counts[("a", "out")] == 3

    def test_a_cycle_whose_counts_only_follow_each_other_is_refused(self) -> None:
        import warnings

        from rasl.graph import PortTypeError

        builder = GraphBuilder()
        builder.add_node(_Node("a", OutputPortSpec(MatrixPayload, same_as="in")))
        builder.add_node(_Node("b", OutputPortSpec(MatrixPayload, same_as="in")))
        builder.connect("a", "out", "b", "in")
        builder.connect("b", "out", "a", "in")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with pytest.raises(PortTypeError, match="Element count unknown"):
                builder.build()

    def test_a_hook_gets_each_inputs_count_and_components(self) -> None:
        seen: list[InputSize] = []

        class Hooked(_Node):
            def output_counts(self, inputs):
                seen.append(inputs["in"])
                return {"out": 2}

        builder = GraphBuilder()
        builder.add_node(_Node("a", OutputPortSpec(MatrixPayload, count=4, components=3)))
        builder.add_node(Hooked("h", OutputPortSpec(MatrixPayload)))
        builder.add_node(_Node("z", OutputPortSpec(MatrixPayload, count=1)))
        builder.connect("a", "out", "h", "in")
        builder.connect("h", "out", "z", "in")
        plan = builder.build()
        assert seen[-1] == InputSize(4, 3)
        assert plan.input_counts[("z", "in")] == 2
