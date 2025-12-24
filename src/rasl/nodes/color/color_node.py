"""Universal color conversion node.

This module provides ColorNode, a configurable transform node that converts
between color spaces using the colour-science library. OKLCH is the default
output model for perceptually uniform color mixing.

Pull-based: Reads input, converts color model, writes output.

Example config:
    node Color mixer {}           # Default: oklch output
    node Color toRgb rgb {}       # Output sRGB
    node Color toHsl hsl {}       # Output HSL
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from rasl.engine.frames import (
    ColorPayload,
    HsbkColorPayload,
    HslColorPayload,
    LinearRgbColorPayload,
    MatrixPayload,
    OkhslColorPayload,
    OkhsvColorPayload,
    OklabColorPayload,
    OklchColorPayload,
    Rec709RgbPrimeColorPayload,
    RgbColorPayload,
    RgbwColorPayload,
)
from rasl.engine.nodes import BaseNode
from rasl.engine.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.engine.registry import node
from rasl.engine.tick import TickContext
from rasl.nodes.models import TransformNodeConfig

# Map model names to payload classes
FRAME_CLASSES: dict[str, type[ColorPayload]] = {
    "oklch": OklchColorPayload,
    "oklab": OklabColorPayload,
    "okhsl": OkhslColorPayload,
    "okhsv": OkhsvColorPayload,
    "hsbk": HsbkColorPayload,
    "srgb": RgbColorPayload,
    "rgbw": RgbwColorPayload,
    "rgb": LinearRgbColorPayload,
    "hsl": HslColorPayload,
    "linear": LinearRgbColorPayload,
    "rec709": Rec709RgbPrimeColorPayload,
    "rec709_rgb_prime": Rec709RgbPrimeColorPayload,
}

# Valid model names for config validation
ColorModel = Literal[
    "oklch",
    "oklab",
    "okhsl",
    "okhsv",
    "hsbk",
    "srgb",
    "rgbw",
    "rgb",
    "hsl",
    "linear",
    "rec709",
    "rec709_rgb_prime",
]


@node("ColorNode", "Color")
class ColorNode(BaseNode):
    """Universal color space converter.

    Converts any input to the specified color model.

    The color model can be specified as a positional argument in the config:
        node Color mixer {}           # Default: oklch output
        node Color toRgb rgb {}       # Output sRGB
        node Color toHsl hsl {}       # Output HSL

    Or as a config property:
        node Color toRgb { model srgb; }

    Attributes:
        inputs: Single 'color' port accepting array or color payloads.
        outputs: Single 'color' port emitting the converted color payload.
    """

    class Config(TransformNodeConfig):
        """Configuration for ColorNode.

        Attributes:
            model: Target color model (required).
        """

        model: ColorModel  # type: ignore[assignment]

    # Class-level ports
    inputs = PortGroup.inputs(color=InputPortSpec((MatrixPayload, ColorPayload)))
    outputs = PortGroup.outputs(color=OutputPortSpec(ColorPayload))

    def __init__(self, config: Config) -> None:
        """Initialize the ColorNode.

        Args:
            config: Validated configuration with target model.
        """
        super().__init__(config)
        self._model = config.model
        self._frame_cls = self._frame_class_for(self._model)

    @staticmethod
    def _frame_class_for(model: str) -> type[ColorPayload]:
        cls = FRAME_CLASSES.get(model)
        if cls is None:
            raise ValueError(f"Unsupported color model '{model}'")
        return cls

    async def pull(self, tick: TickContext) -> None:
        """Read input, convert color model, write output."""
        frame = self.inputs.color.read()
        if frame is None:
            return

        payload = frame.payload

        target_frame_cls = self._frame_cls
        target_model = self._model

        # Convert via payload API (type-driven)
        if isinstance(payload, ColorPayload):
            out_payload = (
                payload if isinstance(payload, target_frame_cls) else payload.to_model(target_frame_cls)
            )
        else:
            arr = np.asarray(payload, dtype=np.float32)
            try:
                out_payload = target_frame_cls(arr, encoding=target_model)
            except TypeError:
                out_payload = target_frame_cls(arr)

        self.outputs.color.write(frame.with_payload(out_payload))
