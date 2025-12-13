"""Color processing nodes and utilities.

This package contains nodes for color space conversion and composition,
as well as the color conversion utilities.

Nodes:
    - ColorNode: Universal color space converter
    - ColorCorrectionNode: Per-LED-type color correction
    - ComposeNode: Interleave multiple inputs into color output

Utilities:
    - MODELS: Set of supported color model names
    - DEFAULT_MODEL: Default color model (oklch)
"""

from .color_node import ColorNode
from .compose_node import ComposeNode
from .correction_node import ColorCorrectionNode

__all__ = [
    "ColorNode",
    "ColorCorrectionNode",
    "ComposeNode",
]
