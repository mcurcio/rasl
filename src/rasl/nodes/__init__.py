"""RASL Nodes - Concrete node implementations for the processing graph.

This package provides the built-in node types for common operations:

Source Nodes:
    - SacnSourceNode: Receive sACN/E1.31 DMX data from network
    - SineSourceNode: Generate virtual sine-wave test data
    - WaveformNode: Configurable waveform generator (sine, triangle, attack_decay)
    - SeededRandomNode: Deterministic per-channel random values (TwinkleFOX style)

Transform Nodes:
    - UniversePatchTransform: Remap DMX channels between universes
    - ColorNode: Universal color space converter (oklch, oklab, srgb, hsl)
    - ComposeNode: Interleave multiple inputs into single output
    - MathNode: Element-wise math operations (multiply, add, screen, lerp)
    - TwinkleEffectNode: TwinkleFOX-style brightness modulation

Sink Nodes:
    - SacnSinkNode: Transmit sACN/E1.31 DMX data to network
    - DdpSinkNode: Transmit RGB pixel data via DDP protocol
    - ConsoleSinkNode: Log frames to the console/logger

Nodes are registered via the @node decorator and discovered by the
config loader through the registry. Importing this module triggers
registration of all built-in nodes.

Example configuration (see ``sample.conf``)::

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

# Importing these modules triggers @node decorator registration
from .color_node import ColorNode
from .compose_node import ComposeNode
from .console_sink import ConsoleSinkNode
from .ddp_sink import DdpSinkNode
from .math_node import MathNode
from .sacn_sink import SacnSinkNode
from .sacn_source import SacnSourceNode
from .seeded_random_node import SeededRandomNode
from .sine_source import SineSourceNode
from .twinkle_effect import TwinkleEffectNode
from .universe_patch import SegmentConfig, UniversePatchTransform
from .waveform_node import WaveformNode

__all__ = [
    "ColorNode",
    "ComposeNode",
    "ConsoleSinkNode",
    "DdpSinkNode",
    "MathNode",
    "SacnSinkNode",
    "SacnSourceNode",
    "SeededRandomNode",
    "SegmentConfig",
    "SineSourceNode",
    "TwinkleEffectNode",
    "UniversePatchTransform",
    "WaveformNode",
]
