"""Color correction transform node.

This module provides ColorCorrectionNode, which applies per-LED-type
color corrections including gamma, saturation, brightness, and RGB
channel scaling. Corrections are applied in linear RGB space for
physically correct results.

Pull-based: Reads input, applies correction, writes output.

Example config:
    node ColorCorrection warm_white {
        gamma 2.2;
        saturation 1.2;
        brightness 0.9;
        r_scale 1.0;
        g_scale 0.95;
        b_scale 0.85;  # Reduce blue for warmer output
        
        connect color_source;
    }
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from rasl.engine.nodes import BaseNode, NodeContext
from rasl.engine.frames import ColorPayload, Frame, MatrixPayload, RgbColorPayload
from rasl.engine.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.engine.registry import node
from rasl.engine.tick import TickContext
from rasl.nodes.models import TransformNodeConfig

from .convert import convert

if TYPE_CHECKING:
    from numpy.typing import NDArray


@node("ColorCorrectionNode", "ColorCorrection")
class ColorCorrectionNode(BaseNode):
    """Transform node for per-LED-type color correction.

    Applies color corrections in linear RGB space for physically correct
    results. The correction pipeline is:
    
    1. Convert input to linear RGB (remove gamma)
    2. Apply RGB channel scaling (white balance / color temperature)
    3. Apply saturation adjustment
    4. Apply brightness scaling
    5. Apply output gamma
    6. Convert back to sRGB

    All operations are performed in linear space except the final gamma
    encoding, which produces the output suitable for LED drivers.

    Example config:
        rasl {
            # Warm white LED profile
            node ColorCorrection warm_leds {
                gamma 2.2;
                saturation 1.1;
                brightness 0.85;
                r_scale 1.0;
                g_scale 0.92;
                b_scale 0.78;
                
                connect color_source;
            }
            
            # Cool white LED profile  
            node ColorCorrection cool_leds {
                gamma 2.4;
                saturation 1.0;
                brightness 1.0;
                r_scale 0.95;
                g_scale 1.0;
                b_scale 1.05;
                
                connect color_source;
            }
        }
    """

    class Config(TransformNodeConfig):
        """Configuration for ColorCorrectionNode.
        
        Attributes:
            gamma: Output gamma (typical: 2.2 for sRGB, 2.4-2.8 for LEDs)
            saturation: Saturation multiplier (1.0 = unchanged, >1 = more vivid)
            brightness: Overall brightness multiplier (1.0 = unchanged)
            r_scale: Red channel multiplier for white balance
            g_scale: Green channel multiplier for white balance
            b_scale: Blue channel multiplier for white balance
            r_offset: Red channel offset (added after scaling)
            g_offset: Green channel offset (added after scaling)
            b_offset: Blue channel offset (added after scaling)
        """

        gamma: float = Field(2.2, ge=1.0, le=4.0, description="Output gamma curve")
        saturation: float = Field(1.0, ge=0.0, le=3.0, description="Saturation multiplier")
        brightness: float = Field(1.0, ge=0.0, le=2.0, description="Brightness multiplier")
        
        # RGB channel scaling (white balance)
        r_scale: float = Field(1.0, ge=0.0, le=2.0, description="Red channel scale")
        g_scale: float = Field(1.0, ge=0.0, le=2.0, description="Green channel scale")
        b_scale: float = Field(1.0, ge=0.0, le=2.0, description="Blue channel scale")
        
        # RGB channel offsets (black level adjustment)
        r_offset: float = Field(0.0, ge=-0.5, le=0.5, description="Red channel offset")
        g_offset: float = Field(0.0, ge=-0.5, le=0.5, description="Green channel offset")
        b_offset: float = Field(0.0, ge=-0.5, le=0.5, description="Blue channel offset")

    # Class-level ports
    inputs = PortGroup.inputs(input=InputPortSpec((MatrixPayload, ColorPayload)))
    outputs = PortGroup.outputs(out=OutputPortSpec(ColorPayload))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._gamma = config.gamma
        self._saturation = config.saturation
        self._brightness = config.brightness
        self._r_scale = config.r_scale
        self._g_scale = config.g_scale
        self._b_scale = config.b_scale
        self._r_offset = config.r_offset
        self._g_offset = config.g_offset
        self._b_offset = config.b_offset
        
        # Pre-compute scale array for vectorized operations
        self._rgb_scale = np.array(
            [self._r_scale, self._g_scale, self._b_scale],
            dtype=np.float32
        )
        self._rgb_offset = np.array(
            [self._r_offset, self._g_offset, self._b_offset],
            dtype=np.float32
        )

    async def pull(self, tick: TickContext) -> None:
        """Apply color correction to input."""
        frame = self.inputs.input.read()
        if frame is None:
            return

        payload = frame.payload
        
        # Get color data
        if isinstance(payload, ColorPayload):
            src_model = payload.model
            data = payload.data.copy()
        else:
            # Assume sRGB if we get a plain MatrixFrame
            src_model = "srgb"
            data = np.asarray(payload, dtype=np.float32).copy()

        # Validate: must be RGB triplets
        if len(data) % 3 != 0:
            self.outputs.out.write(frame)
            return
            
        num_pixels = len(data) // 3

        # Step 1: Convert to linear RGB
        if src_model == "linear":
            linear = data
        else:
            linear = convert(data, src_model, "linear")
        
        # Reshape to (num_pixels, 3) for vectorized operations
        rgb = linear.reshape(num_pixels, 3)
        
        # Step 2: Apply RGB channel scaling (white balance)
        rgb = rgb * self._rgb_scale + self._rgb_offset
        
        # Step 3: Apply saturation adjustment (in linear space)
        if self._saturation != 1.0:
            # Compute luminance (Rec. 709 coefficients for linear RGB)
            luma = 0.2126 * rgb[:, 0] + 0.7152 * rgb[:, 1] + 0.0722 * rgb[:, 2]
            luma = luma[:, np.newaxis]  # Shape: (num_pixels, 1)
            
            # Lerp between grayscale and color
            rgb = luma + self._saturation * (rgb - luma)
        
        # Step 4: Apply brightness
        if self._brightness != 1.0:
            rgb = rgb * self._brightness
        
        # Step 5: Clamp to valid range before gamma
        rgb = np.clip(rgb, 0.0, 1.0)
        
        # Step 6: Apply output gamma
        if self._gamma != 1.0:
            rgb = np.power(rgb, 1.0 / self._gamma)
        
        # Flatten back to 1D
        output_data = rgb.reshape(-1).astype(np.float32)

        # Output as sRGB (gamma already applied)
        output_payload = RgbColorPayload(output_data)
        self.outputs.out.write(frame.with_payload(output_payload))
