"""Frame and payload types for the RASL processing DAG.

This package provides the core data types for frames flowing through
the node graph:

- FramePayload: Abstract base for all payload types
- MatrixPayload: Base for all numeric signal types
- ColorPayload: Color data with model tag and conversion
- Frame: Immutable container with routing metadata

Submodules:
- base: FramePayload, PayloadDescriptor
- matrix: MatrixPayload, BoolPayload
- color: ColorPayload and all color model subclasses
- frame: Frame dataclass
"""

from .base import FramePayload, PayloadDescriptor
from .matrix import MatrixPayload, BoolPayload
from .color import (
    ColorPayload,
    RgbColorPayload,
    HslColorPayload,
    OklchColorPayload,
    OklabColorPayload,
    OkhslColorPayload,
    OkhsvColorPayload,
    LinearRgbColorPayload,
    Rec709RgbPrimeColorPayload,
)
from .frame import Frame, Metadata

__all__ = [
    # Base
    "FramePayload",
    "PayloadDescriptor",
    # Matrix
    "MatrixPayload",
    "BoolPayload",
    # Color
    "ColorPayload",
    "RgbColorPayload",
    "HslColorPayload",
    "OklchColorPayload",
    "OklabColorPayload",
    "OkhslColorPayload",
    "OkhsvColorPayload",
    "LinearRgbColorPayload",
    "Rec709RgbPrimeColorPayload",
    # Frame
    "Frame",
    "Metadata",
]
