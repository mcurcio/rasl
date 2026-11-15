"""Color: the models rasl knows, converting between them, and color payloads.

- ``rasl.color.models``: model names and component counts
- ``rasl.color.convert``: ``convert(pixels, from_model, to_model)``
- ``rasl.color.payloads``: ``ColorPayload`` and one subclass per model, each
  able to convert itself with ``to_model``
"""

from rasl.color.convert import convert
from rasl.color.models import normalize_model
from rasl.color.payloads import (
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

__all__ = [
    "ColorPayload",
    "HsbkColorPayload",
    "HslColorPayload",
    "LinearRgbColorPayload",
    "OkhslColorPayload",
    "OkhsvColorPayload",
    "OklabColorPayload",
    "OklchColorPayload",
    "Rec709RgbPrimeColorPayload",
    "RgbColorPayload",
    "RgbwColorPayload",
    "convert",
    "normalize_model",
]
