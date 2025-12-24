"""Effect nodes for animation and modulation.

This package contains nodes for generating animated effects:
    - WaveformNode: Configurable waveform generator (sine, triangle, attack_decay)
    - SeededRandomNode: Deterministic per-channel random values
    - TwinkleEffectNode: TwinkleFOX-style brightness modulation
    - MathNode: Element-wise math operations
    - RangeMapNode: Per-channel range remapping
    - MatrixMultiplyNode: Fixed matrix channel mixing
"""

from .math import MathNode
from .cron import CronNode
from .crossfade import CrossfadeNode
from .matrix_multiply import MatrixMultiplyNode
from .range_map import RangeMapNode
from .twinkle import TwinkleEffectNode
from .waveform import WaveformNode

__all__ = [
    "CronNode",
    "CrossfadeNode",
    "MatrixMultiplyNode",
    "MathNode",
    "RangeMapNode",
    "TwinkleEffectNode",
    "WaveformNode",
]
