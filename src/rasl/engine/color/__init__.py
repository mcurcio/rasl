"""Color conversion utilities for RASL.

This module provides color space conversion using the colour-science library.
OKLCH is the default internal color model for perceptually uniform mixing.

Supported models:
    - oklch: Perceptually uniform cylindrical (L, C, H) - DEFAULT
    - oklab: Perceptually uniform cartesian (L, a, b)
    - srgb: Standard RGB with gamma encoding
    - hsl: Hue, Saturation, Lightness (legacy)

Example:
    >>> from rasl.engine.color import convert
    >>> import numpy as np
    >>> hsl_data = np.array([[0.5, 1.0, 0.5]], dtype=np.float32)
    >>> oklch_data = convert(hsl_data, "hsl", "oklch")
"""

from .convert import MODELS, DEFAULT_MODEL, convert

__all__ = ["MODELS", "DEFAULT_MODEL", "convert"]
