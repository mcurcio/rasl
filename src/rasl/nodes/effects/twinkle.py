"""TwinkleEffect transform node.

Applies TwinkleFOX-style modulation to incoming color data.
Each pixel gets a random phase offset and speed multiplier, creating
organic, non-synchronized twinkling.

Two modes are supported:
- **brightness**: Multiply RGB by envelope → fade to black (classic twinkle)
- **whiteness**: Reduce OkHSL saturation by envelope → fade to white (sparkle)

Pull-based: Uses tick.t for timing instead of internal clock.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from rasl.engine.nodes import BaseNode, NodeContext
from rasl.engine.frames import ColorPayload, Frame, OkhslColorPayload, RgbColorPayload
from rasl.engine.ports import InputPortSpec, OutputPortSpec, PortGroup
from rasl.engine.registry import node
from rasl.engine.tick import TickContext
from rasl.nodes.models import TransformNodeConfig

TwinkleMode = Literal["brightness", "whiteness"]


def attack_decay_wave(phase: NDArray[np.float32], attack_ratio: float = 0.33) -> NDArray[np.float32]:
    """Attempt to perf-optimize the attack-decay waveform.

    Fast attack (attack_ratio of cycle), slow decay (rest of cycle).
    This is the classic TwinkleFOX brightness envelope.

    Args:
        phase: Phase values in [0, 1] range
        attack_ratio: Fraction of cycle for attack (default 0.33 = 1/3)

    Returns:
        Brightness values in [0, 1] range
    """
    phase = phase % 1.0
    result = np.where(
        phase < attack_ratio,
        phase / attack_ratio,  # Attack: ramp up
        1.0 - (phase - attack_ratio) / (1.0 - attack_ratio),  # Decay: ramp down
    )
    return result.astype(np.float32)


@node("TwinkleEffectNode", "TwinkleEffect")
class TwinkleEffectNode(BaseNode):
    """Applies TwinkleFOX-style twinkle effect to color input.

    This transform node modulates incoming color data using per-pixel
    random phase offsets and speed multipliers. The result is organic,
    non-synchronized twinkling that mimics holiday lights.

    Two modes are available:
    - **brightness**: Multiply RGB by envelope → LEDs fade to black
    - **whiteness**: Reduce saturation by envelope → LEDs fade to white

    The effect uses:
    - Per-pixel phase offsets (stable across frames, from seed)
    - Per-pixel speed multipliers (1x to max_speed)
    - Attack-decay waveform (fast rise, slow fall)

    Example config:
        node TwinkleEffect twinkle {
            seed 11337;
            mode brightness;  # or "whiteness"
            frequency_hz 0.3;
            attack_ratio 0.33;
            min_speed 1.0;
            max_speed 3.0;

            connect color_source;
        }
    """

    class Config(TransformNodeConfig):
        """Configuration for TwinkleEffectNode."""

        seed: int = Field(42, description="Random seed for deterministic per-pixel values")
        mode: TwinkleMode = Field(
            "brightness",
            description="Twinkle mode: 'brightness' (fade to black) or 'whiteness' (fade to white)"
        )
        frequency_hz: float = Field(
            0.3, ge=0.01, le=10.0, description="Base twinkle frequency in Hz"
        )
        attack_ratio: float = Field(
            0.33, ge=0.1, le=0.9, description="Fraction of cycle for attack (rise)"
        )
        min_speed: float = Field(
            1.0, ge=0.1, le=10.0, description="Minimum speed multiplier"
        )
        max_speed: float = Field(
            3.0, ge=0.1, le=10.0, description="Maximum speed multiplier"
        )

    # Class-level ports
    inputs = PortGroup.inputs(input=InputPortSpec(ColorPayload))
    outputs = PortGroup.outputs(out=OutputPortSpec(ColorPayload))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._seed = config.seed
        self._mode: TwinkleMode = config.mode
        self._frequency_hz = config.frequency_hz
        self._attack_ratio = config.attack_ratio
        self._min_speed = config.min_speed
        self._max_speed = config.max_speed

        # Will be initialized on first frame (need to know channel count)
        self._phase_offsets: NDArray[np.float32] | None = None
        self._speed_multipliers: NDArray[np.float32] | None = None
        self._num_pixels: int | None = None

    def _initialize_for_size(self, num_pixels: int) -> None:
        """Initialize per-pixel random values for given pixel count."""
        if self._num_pixels == num_pixels:
            return  # Already initialized for this size

        self._num_pixels = num_pixels

        # Generate phase offsets [0, 1)
        rng_phase = np.random.Generator(np.random.PCG64(self._seed))
        self._phase_offsets = rng_phase.random(num_pixels, dtype=np.float32)

        # Generate speed multipliers [min_speed, max_speed]
        rng_speed = np.random.Generator(np.random.PCG64(self._seed + 1))
        self._speed_multipliers = (
            rng_speed.random(num_pixels, dtype=np.float32)
            * (self._max_speed - self._min_speed)
            + self._min_speed
        ).astype(np.float32)

    async def pull(self, tick: TickContext) -> None:
        """Apply twinkle effect using scheduler's authoritative time."""
        frame = self.inputs.input.read()
        if frame is None:
            return

        payload = frame.payload
        
        # Get color data and metadata
        if isinstance(payload, ColorPayload):
            original_model = payload.model
            original_encoding = payload.encoding
            data = payload.data.copy()  # Copy to avoid mutating original
        else:
            # Treat non-color payloads as sRGB matrices
            original_model = "srgb"
            original_encoding = "srgb"
            data = np.asarray(payload, dtype=np.float32).copy()

        if data.ndim == 1:
            data = data.reshape(-1, 1)
        if data.ndim != 2:
            self.outputs.out.write(frame)
            return

        num_pixels = data.shape[0]
        if num_pixels <= 0:
            return

        # Initialize per-pixel values if needed
        self._initialize_for_size(num_pixels)
        assert self._phase_offsets is not None
        assert self._speed_multipliers is not None

        # Calculate current phase for each pixel using scheduler time
        t = tick.t
        base_phase = t * self._frequency_hz
        pixel_phases = (
            base_phase * self._speed_multipliers + self._phase_offsets
        ) % 1.0

        # Generate envelope [0, 1]
        envelope = attack_decay_wave(pixel_phases, self._attack_ratio)

        if self._mode == "brightness":
            # Brightness mode: multiply RGB by envelope → fade to black
            # NOTE: We always work in sRGB for brightness mode because
            # OkHSL has numerical instability at very low lightness values
            # that produces wrong saturated colors instead of near-black.
            if original_model != "srgb":
                rgb_frame = ColorPayload(data, model=original_model, encoding=original_encoding)
                rgb = rgb_frame.to_model(RgbColorPayload).data.copy()
            else:
                rgb = data

            # Apply envelope to the first 3 channels (RGB)
            if rgb.shape[1] >= 3:
                rgb[:, :3] *= envelope[:, np.newaxis]

            # Output as sRGB - ColorNode will handle any needed conversion
            output_frame = ColorPayload(
                rgb.astype(np.float32),
                model="srgb",
                encoding=original_encoding,
            )
                
        else:  # whiteness mode
            # Whiteness mode: reduce saturation by envelope → fade to white
            # For OkHSL, we can directly modify the S channel (much faster)
            if original_model == "okhsl":
                hsl = data
            else:
                # Convert to OkHSL for saturation manipulation
                color_frame = ColorPayload(data, model=original_model, encoding=original_encoding)
                hsl = color_frame.to_model(OkhslColorPayload).data.copy()

            # Reduce saturation (channel 1) by envelope
            if hsl.shape[1] >= 2:
                hsl[:, 1] = hsl[:, 1] * (1.0 - envelope)

            # Output as OkHSL - don't convert back since ColorNode will handle it
            output_frame = ColorPayload(
                hsl.astype(np.float32),
                model="okhsl",
                encoding=original_encoding,
            )

        # Write with modulated frame
        self.outputs.out.write(frame.with_payload(output_frame))
