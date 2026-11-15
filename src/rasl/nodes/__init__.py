"""RASL Nodes - Concrete node implementations for the processing graph.

This package provides the built-in node types organized by function:

nodes/
├── effects/            - Animation and modulation nodes
│   ├── waveform.py     - WaveformNode (sine, triangle, attack_decay)
│   ├── seeded_random.py - SeededRandomNode (deterministic per-channel random)
│   ├── twinkle.py      - TwinkleEffectNode (TwinkleFOX-style modulation)
│   └── math.py         - MathNode (element-wise operations)
├── color/              - Color processing nodes
│   ├── convert.py      - Color conversion utilities
│   ├── color_node.py   - ColorNode (universal color converter)
│   └── compose_node.py - ComposeNode (interleave inputs)
└── debug/              - Testing and debugging nodes
    ├── console_sink.py - ConsoleSinkNode (log to console)
    └── sine_source.py  - SineSourceNode (test waveform)

Protocol nodes are in rasl.packages:
    - rasl.packages.sacn: SacnSourceNode, SacnSinkNode
    - rasl.packages.ddp: DdpSinkNode

Nodes are registered via the @node decorator and discovered by the
config loader through the registry, which imports this package as the
"rasl.nodes" entry point named "builtin". Importing it registers every
built-in node. The config base classes (BaseNodeConfig and the Source,
Transform and Sink bases) are in rasl.engine.nodes.config.

Example configuration::

    rasl {
        node SacnSource sacnSource {
            universes 1 2;
        }
        node Color toOklch {}  # Default: oklch output
        node Color toRgb rgb {}  # Explicit rgb output
        node SacnSink sacnSink0 {
            input_port universe0;
            target_host "10.0.60.30";
            target_universe 0;
        }
    }
"""

# Importing a node module registers its class (@node)
from .color.color_node import ColorNode
from .color.compose_node import ComposeNode
from .debug.console_sink import ConsoleSinkNode
from .debug.sine_source import SineSourceNode
from .effects.cron import CronNode
from .effects.crossfade import CrossfadeNode
from .effects.math import MathNode
from .effects.matrix_multiply import MatrixMultiplyNode
from .effects.random_map import RandomMapNode
from .effects.range_map import RangeMapNode
from .effects.seeded_random import SeededRandomNode
from .effects.smooth import SmoothNode
from .effects.twinkle import TwinkleEffectNode
from .effects.waveform import WaveformNode
from .literal_node import LiteralNode

__all__ = [
    "ColorNode",
    "ComposeNode",
    "ConsoleSinkNode",
    "CronNode",
    "CrossfadeNode",
    "LiteralNode",
    "MathNode",
    "MatrixMultiplyNode",
    "RandomMapNode",
    "RangeMapNode",
    "SeededRandomNode",
    "SineSourceNode",
    "SmoothNode",
    "TwinkleEffectNode",
    "WaveformNode",
]
