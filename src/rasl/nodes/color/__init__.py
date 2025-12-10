"""Color processing nodes and utilities.

This package contains nodes for color space conversion and composition,
as well as the color conversion utilities.

Nodes:
    - ColorNode: Universal color space converter
    - ColorCorrectionNode: Per-LED-type color correction
    - ComposeNode: Interleave multiple inputs into color output

Utilities:
    - convert: Convert between color spaces
    - MODELS: Set of supported color model names
    - DEFAULT_MODEL: Default color model (oklch)
"""

from .color_node import ColorNode
from .compose_node import ComposeNode
from .correction_node import ColorCorrectionNode
from .convert import DEFAULT_MODEL, MODELS, convert

__all__ = [
    "ColorNode",
    "ColorCorrectionNode",
    "ComposeNode",
    "convert",
    "DEFAULT_MODEL",
    "MODELS",
]
