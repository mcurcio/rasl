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

from rasl.engine.frames.base import FramePayload, PayloadDescriptor
from rasl.engine.frames.color import (
    ColorPayload,
    HsbkColorPayload,
    HslColorPayload,
    LinearRgbColorPayload,
    OkhslColorPayload,
    OkhsvColorPayload,
    OklabColorPayload,
    OklchColorPayload,
    Rec709RgbPrimeColorPayload,
    RgbColorPayload,
    RgbwColorPayload,
)
from rasl.engine.frames.frame import Frame, Metadata
from rasl.engine.frames.matrix import BoolPayload, MatrixPayload

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
    "RgbwColorPayload",
    "HslColorPayload",
    "OklchColorPayload",
    "OklabColorPayload",
    "OkhslColorPayload",
    "OkhsvColorPayload",
    "LinearRgbColorPayload",
    "Rec709RgbPrimeColorPayload",
    "HsbkColorPayload",
    # Frame
    "Frame",
    "Metadata",
]
