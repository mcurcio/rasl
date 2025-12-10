"""Effect nodes for animation and modulation.

This package contains nodes for generating animated effects:
    - WaveformNode: Configurable waveform generator (sine, triangle, attack_decay)
    - SeededRandomNode: Deterministic per-channel random values
    - TwinkleEffectNode: TwinkleFOX-style brightness modulation
    - MathNode: Element-wise math operations
"""

from .math import MathNode
from .seeded_random import SeededRandomNode
from .twinkle import TwinkleEffectNode
from .waveform import WaveformNode

__all__ = [
    "MathNode",
    "SeededRandomNode",
    "TwinkleEffectNode",
    "WaveformNode",
]
