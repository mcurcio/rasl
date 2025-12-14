"""RASL Nodes - Concrete node implementations for the processing graph.

This package provides the built-in node types organized by function:

nodes/
├── models.py           - Base config classes (BaseNodeConfig, etc.)
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
config loader through the registry. Importing this module triggers
registration of all built-in nodes.

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

# Base config models (import directly, no circular dependency)
from .models import BaseNodeConfig, SinkNodeConfig, SourceNodeConfig, TransformNodeConfig


def _register_all_nodes() -> None:
    """Import all node modules to trigger @node decorator registration.
    
    This is called by the entry point system to ensure all nodes are
    registered before config loading.
    """
    # Effect nodes
    from .effects.cron import CronNode
    from .effects.crossfade import CrossfadeNode
    from .effects.math import MathNode
    from .effects.seeded_random import SeededRandomNode
    from .effects.twinkle import TwinkleEffectNode
    from .effects.waveform import WaveformNode
    
    # Color nodes
    from .color.color_node import ColorNode
    from .color.compose_node import ComposeNode
    
    # Debug nodes
    from .debug.console_sink import ConsoleSinkNode
    from .debug.sine_source import SineSourceNode
    
    # Utility nodes
    from .literal_node import LiteralNode
    
    # Protocol nodes
    from rasl.packages.sacn import SacnSinkNode, SacnSourceNode
    from rasl.packages.ddp import DdpSinkNode


# NOTE: Node registration is deferred to avoid circular imports.
# Nodes are registered when first accessed via __getattr__ or when
# explicitly imported. The config loader triggers registration by
# importing the node modules it needs.


def __getattr__(name: str):
    """Lazy import for attribute access (for backward compatibility)."""
    # Effect nodes
    if name == "CrossfadeNode":
        from .effects.crossfade import CrossfadeNode
        return CrossfadeNode
    if name == "MathNode":
        from .effects.math import MathNode
        return MathNode
    if name == "SeededRandomNode":
        from .effects.seeded_random import SeededRandomNode
        return SeededRandomNode
    if name == "TwinkleEffectNode":
        from .effects.twinkle import TwinkleEffectNode
        return TwinkleEffectNode
    if name == "WaveformNode":
        from .effects.waveform import WaveformNode
        return WaveformNode
    
    # Color nodes
    if name == "ColorNode":
        from .color.color_node import ColorNode
        return ColorNode
    if name == "ComposeNode":
        from .color.compose_node import ComposeNode
        return ComposeNode
    
    # Debug nodes
    if name == "ConsoleSinkNode":
        from .debug.console_sink import ConsoleSinkNode
        return ConsoleSinkNode
    if name == "SineSourceNode":
        from .debug.sine_source import SineSourceNode
        return SineSourceNode
    
    # Utility nodes
    if name == "LiteralNode":
        from .literal_node import LiteralNode
        return LiteralNode
    
    # Protocol nodes
    if name == "SacnSinkNode":
        from rasl.packages.sacn import SacnSinkNode
        return SacnSinkNode
    if name == "SacnSourceNode":
        from rasl.packages.sacn import SacnSourceNode
        return SacnSourceNode
    if name == "DdpSinkNode":
        from rasl.packages.ddp import DdpSinkNode
        return DdpSinkNode
    
    raise AttributeError(f"module 'rasl.nodes' has no attribute {name!r}")

__all__ = [
    # Config models
    "BaseNodeConfig",
    "SinkNodeConfig",
    "SourceNodeConfig",
    "TransformNodeConfig",
    # Effect nodes
    "CronNode",
    "CrossfadeNode",
    "MathNode",
    "SeededRandomNode",
    "TwinkleEffectNode",
    "WaveformNode",
    # Color nodes
    "ColorNode",
    "ComposeNode",
    # Debug nodes
    "ConsoleSinkNode",
    "SineSourceNode",
    # Utility nodes
    "LiteralNode",
    # Protocol nodes
    "DdpSinkNode",
    "SacnSinkNode",
    "SacnSourceNode",
]
