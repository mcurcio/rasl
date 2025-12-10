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

from typing import TYPE_CHECKING, Literal

import numpy as np

from rasl.engine.base_node import BaseNode
from rasl.engine.frame import (
    ColorPayload,
    Frame,
    HslColorPayload,
    LinearRgbColorPayload,
    OkhslColorPayload,
    OkhsvColorPayload,
    OklabColorPayload,
    OklchColorPayload,
    RgbColorPayload,
)
from rasl.engine.node import NodeContext
from rasl.engine.ports import PortGroup, PortSpec
from rasl.engine.registry import node
from rasl.engine.tick import TickContext
from rasl.nodes.models import TransformNodeConfig

from .convert import DEFAULT_MODEL, convert

if TYPE_CHECKING:
    from numpy.typing import NDArray

# Map model names to payload classes
PAYLOAD_CLASSES: dict[str, type[ColorPayload]] = {
    "oklch": OklchColorPayload,
    "oklab": OklabColorPayload,
    "okhsl": OkhslColorPayload,
    "okhsv": OkhsvColorPayload,
    "srgb": RgbColorPayload,
    "rgb": RgbColorPayload,  # Alias
    "hsl": HslColorPayload,
    "linear": LinearRgbColorPayload,
}

# Valid model names for config validation
ColorModel = Literal["oklch", "oklab", "okhsl", "okhsv", "srgb", "rgb", "hsl", "linear"]


@node("ColorNode", "Color")
class ColorNode(BaseNode):
    """Universal color space converter.

    Converts any input to the specified color model.
    Default output is OKLCH (perceptually uniform, ideal for mixing).

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
            model: Target color model. Default is 'oklch'.
        """

        model: ColorModel = DEFAULT_MODEL  # type: ignore[assignment]

    # Class-level ports
    inputs = PortGroup.inputs(color=PortSpec(accepts=("array", "color")))
    outputs = PortGroup.outputs(color=PortSpec(accepts="color"))

    def __init__(self, config: Config) -> None:
        """Initialize the ColorNode.

        Args:
            config: Validated configuration with target model.
        """
        super().__init__(config)
        # Normalize "rgb" alias to "srgb" for internal use
        self._model = "srgb" if config.model == "rgb" else config.model
        self._payload_cls = PAYLOAD_CLASSES.get(self._model, OklchColorPayload)

    async def pull(self, tick: TickContext) -> None:
        """Read input, convert color model, write output."""
        frame = self.inputs.color.read()
        if frame is None:
            return

        payload = frame.payload

        # Determine source model and data
        if isinstance(payload, ColorPayload):
            src_model = payload.model
            data: NDArray[np.float32] = payload.data
            encoding = payload.encoding
        else:
            # Raw array - assume sRGB
            src_model = "srgb"
            data = np.asarray(payload, dtype=np.float32)
            encoding = "srgb"

        # Convert if needed
        if src_model == self._model:
            out_data = data
        else:
            out_data = convert(data, src_model, self._model)

        # Write with appropriate payload type
        out_payload = self._payload_cls(out_data, encoding=encoding)
        self.outputs.color.write(frame.with_payload(out_payload))
