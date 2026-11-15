"""Color: the models rasl knows, converting between them, and color payloads.

- ``rasl.color.models``: model names and component counts
- ``rasl.color.convert``: ``convert(pixels, from_model, to_model)``
- ``rasl.color.base``: ``ColorPayload``, color data tagged with its model
- ``rasl.color.payloads``: one subclass per model; any of them converts to
  another with ``to_model``
"""

from rasl.color.base import ColorPayload
from rasl.color.convert import convert
from rasl.color.models import normalize_model
from rasl.color.payloads import (
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
