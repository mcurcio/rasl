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

Protocol nodes are in rasl.devices:
    - rasl.devices.sacn: SacnSourceNode, SacnSinkNode
    - rasl.devices.ddp: DdpSinkNode

Nodes are registered via the @node decorator and discovered by the
config loader through the registry, which imports this package as the
"rasl.nodes" entry point named "builtin". Importing it registers every
built-in node. The config base classes (BaseNodeConfig and the Source,
Transform and Sink bases) are in rasl.graph.node.

Example configuration::

    graph {
        node SacnSource sacnSource {
            universes 1 2;
        }
        node Color toOklch oklch { connect sacnSource; }  # convert to OKLCH
        node Color toRgb rgb { connect toOklch; }         # and back to RGB
        node SacnSink sacnSink0 {
            input_port universe0;
            target_host "10.0.60.30";
            target_universe 0;
        }
    }
"""

# Importing a node module registers its class (@node)
from rasl.nodes.color.color_node import ColorNode
from rasl.nodes.color.compose_node import ComposeNode
from rasl.nodes.debug.console_sink import ConsoleSinkNode
from rasl.nodes.debug.sine_source import SineSourceNode
from rasl.nodes.effects.cron import CronNode
from rasl.nodes.effects.crossfade import CrossfadeNode
from rasl.nodes.effects.math import MathNode
from rasl.nodes.effects.matrix_multiply import MatrixMultiplyNode
from rasl.nodes.effects.random_map import RandomMapNode
from rasl.nodes.effects.range_map import RangeMapNode
from rasl.nodes.effects.seeded_random import SeededRandomNode
from rasl.nodes.effects.smooth import SmoothNode
from rasl.nodes.effects.twinkle import TwinkleEffectNode
from rasl.nodes.effects.waveform import WaveformNode
from rasl.nodes.literal_node import LiteralNode

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
