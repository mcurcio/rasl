"""The built-in nodes, two of each class, loaded from config text and pulled by the runtime.

Unit tests of one node cannot see a class that shares state between its instances
(rasl-e7j) or a node that fails only when the runtime pulls it; this can (rasl-pd0.35).
"""

from __future__ import annotations

import anyio
import numpy as np
import pytest

from rasl.config.build import parse_config
from rasl.graph.node import ensure_nodes_loaded
from rasl.runtime import Runtime

CONFIG = """
graph {
    node Waveform wave_a { shape sawtooth; frequency_hz 1; output_channels 4; }
    node Waveform wave_b { shape sine; frequency_hz 2; output_channels 6; }

    node SeededRandom random_a { seed 1; output_channels 4; }
    node SeededRandom random_b { seed 2; output_channels 6; output_type binary; density 0.5; }

    node literal red color:srgb [[1, 0, 0]];
    node literal gains matrix [[1.0, 0.9, 0.8]];

    node cron always;
    node cron never 0 0 31 2;

    node SineSource sine_a { output_channels 2; fps 100; }
    node SineSource sine_b { output_channels 3; fps 100; }

    node Compose hsl_a {
        ports { hue; saturation; lightness; }
        output_type color:okhsl;
        connect wave_a hue;
        fill saturation 1;
        fill lightness 0.5;
    }
    node Compose hsl_b {
        ports { hue; saturation; lightness; }
        output_type color:okhsl;
        connect wave_b hue;
        connect random_b saturation;
        fill lightness 0.5;
    }

    node Color rgb_a rgb { connect hsl_a; }
    node Color rgb_b rgb { connect hsl_b; }

    node TwinkleEffect twinkle_a { mode brightness; connect rgb_a; }
    node TwinkleEffect twinkle_b { mode whiteness; connect rgb_b; }

    node ColorCorrection corrected_a { gamma 1.0; connect twinkle_a; }
    node ColorCorrection corrected_b { brightness 0.5; connect rgb_b; }

    node ConsoleSink sink_a { fps 50; connect corrected_a; }
    node ConsoleSink sink_b { fps 50; connect corrected_b; }
    node ConsoleSink sink_twinkle { fps 50; connect twinkle_b; }
    node ConsoleSink sink_random { fps 50; connect random_a; }
    node ConsoleSink sink_red { fps 50; connect red; }
    node ConsoleSink sink_gains { fps 50; connect gains; }
    node ConsoleSink sink_always { fps 50; connect always; }
    node ConsoleSink sink_never { fps 50; connect never; }
    node ConsoleSink sink_sine_a { fps 50; connect sine_a; }
    node ConsoleSink sink_sine_b { fps 50; connect sine_b; }
}
"""


@pytest.fixture(scope="module")
async def ran() -> Runtime:
    """The runtime after a quarter of a second of CONFIG."""
    ensure_nodes_loaded()
    runtime = Runtime(parse_config(CONFIG))
    with anyio.move_on_after(0.25):
        await runtime.run()
    return runtime


def _last(runtime: Runtime, node_id: str) -> np.ndarray:
    """The data ``node_id`` last delivered, read where its consumer reads it."""
    edge = runtime.plan.adjacency[node_id][0]
    frame = runtime.plan.nodes[edge.target].inputs.get(edge.target_port).read()
    assert frame is not None, f"{node_id} delivered nothing to {edge.target}.{edge.target_port}"
    return np.asarray(getattr(frame.payload, "data", frame.payload))


def test_every_node_was_pulled_and_none_failed(ran: Runtime) -> None:
    stats = ran.monitor.get_all_stats()
    failed = {node_id: repr(s.last_error) for node_id, s in stats.items() if s.failure_count}
    assert failed == {}
    pulled = set(ran.plan.nodes) - {"sine_a", "sine_b"}  # SineSource writes on its own timer
    assert pulled <= {node_id for node_id, s in stats.items() if s.success_count > 0}


@pytest.mark.parametrize(
    ("node_id", "shape"),
    [
        ("wave_a", (4, 1)),
        ("wave_b", (6, 1)),
        ("random_a", (4, 1)),
        ("random_b", (6, 1)),
        ("red", (1, 3)),
        ("gains", (1, 3)),
        ("always", (1, 1)),
        ("never", (1, 1)),
        ("sine_a", (2, 1)),
        ("sine_b", (3, 1)),
        ("hsl_a", (4, 3)),
        ("hsl_b", (6, 3)),
        ("rgb_a", (4, 3)),
        ("rgb_b", (6, 3)),
        ("twinkle_a", (4, 3)),
        ("twinkle_b", (6, 3)),
        ("corrected_a", (4, 3)),
        ("corrected_b", (6, 3)),
    ],
)
def test_each_instance_writes_its_own_shape(ran: Runtime, node_id: str, shape: tuple[int, int]) -> None:
    """Two instances of one class have different sizes here: shared state would show."""
    data = _last(ran, node_id)
    assert data.shape == shape
    assert np.isfinite(data.astype(np.float32)).all()


def test_the_values_are_the_configured_ones(ran: Runtime) -> None:
    np.testing.assert_allclose(_last(ran, "red"), [[1, 0, 0]])
    np.testing.assert_allclose(_last(ran, "gains"), [[1.0, 0.9, 0.8]], atol=1e-6)
    assert bool(_last(ran, "always").item()) is True
    assert bool(_last(ran, "never").item()) is False  # 31 February
    assert set(np.unique(_last(ran, "random_b"))) <= {0.0, 1.0}
    assert not np.array_equal(_last(ran, "random_a")[:4], _last(ran, "random_b")[:4])
    for node_id in ("rgb_a", "rgb_b", "corrected_a", "corrected_b", "twinkle_a"):
        data = _last(ran, node_id)
        assert data.min() >= 0.0 and data.max() <= 1.0
