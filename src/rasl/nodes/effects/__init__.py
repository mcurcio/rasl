"""Effect nodes for animation and modulation.

This package contains nodes for generating animated effects:
    - WaveformNode: Configurable waveform generator (sine, triangle, attack_decay)
    - SeededRandomNode: Deterministic per-channel random values
    - TwinkleEffectNode: TwinkleFOX-style brightness modulation
    - MathNode: Element-wise math operations
    - RangeMapNode: Per-channel range remapping
    - MatrixMultiplyNode: Fixed matrix channel mixing
    - ReshapeNode: Regroups a matrix's values into rows of a set width
"""

from rasl.nodes.effects.cron import CronNode
from rasl.nodes.effects.crossfade import CrossfadeNode
from rasl.nodes.effects.math import MathNode
from rasl.nodes.effects.matrix_multiply import MatrixMultiplyNode
from rasl.nodes.effects.range_map import RangeMapNode
from rasl.nodes.effects.reshape import ReshapeNode
from rasl.nodes.effects.twinkle import TwinkleEffectNode
from rasl.nodes.effects.waveform import WaveformNode

__all__ = [
    "CronNode",
    "CrossfadeNode",
    "MatrixMultiplyNode",
    "MathNode",
    "RangeMapNode",
    "ReshapeNode",
    "TwinkleEffectNode",
    "WaveformNode",
]
