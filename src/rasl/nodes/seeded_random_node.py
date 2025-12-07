"""Seeded random source node for deterministic per-channel randomness.

This module provides SeededRandomNode, which generates stable per-channel
random values using a seeded PRNG. This is the key to TwinkleFOX-style
effects where each LED has a unique but stable random offset.

The genius of this approach: instead of storing random values per pixel,
we regenerate them deterministically each frame using a seeded PRNG.
Same seed = same sequence = stable random values with zero RAM overhead.
"""

from __future__ import annotations

import time
from typing import Literal

import anyio
import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from rasl.config.models import SourceNodeConfig
from rasl.engine.base_node import BaseNode
from rasl.engine.frame import ArrayPayload, Frame
from rasl.engine.node import NodeContext
from rasl.engine.ports import PortGroup, PortSpec
from rasl.engine.registry import node


OutputType = Literal["phase", "speed", "uniform", "binary"]


@node("SeededRandomNode", "SeededRandom")
class SeededRandomNode(BaseNode):
    """Source node that generates deterministic per-channel random values.

    Uses a seeded PRNG to generate stable random values for each channel.
    The same seed always produces the same sequence, so each LED gets
    a consistent "random" value across frames.

    Output types:
        - phase: Values in [0, 1] for phase offsets
        - speed: Values in [min_speed, max_speed] for speed multipliers
        - uniform: Raw uniform random values in [min_value, max_value]
        - binary: 0 or 1 based on density threshold

    Example config:
        rasl {
            # Phase offsets for twinkle
            node SeededRandom phases {
                seed 11337;
                output_channels 150;
                output_type phase;
            }

            # Speed multipliers (1x to 3x like TwinkleFOX)
            node SeededRandom speeds {
                seed 22674;
                output_channels 150;
                output_type speed;
                min_speed 1.0;
                max_speed 3.0;
            }

            # Density mask (60% of pixels active)
            node SeededRandom density_mask {
                seed 33911;
                output_channels 150;
                output_type binary;
                density 0.6;
            }
        }
    """

    class Config(SourceNodeConfig):
        """Configuration for SeededRandomNode."""

        output_channels: int = Field(512, ge=1, le=65536, description="Number of output channels")
        seed: int = Field(11337, description="PRNG seed for reproducible randomness")
        output_type: OutputType = Field("phase", description="Type of random output")

        # For speed output type
        min_speed: float = Field(1.0, ge=0.1, le=10.0, description="Minimum speed multiplier")
        max_speed: float = Field(3.0, ge=0.1, le=10.0, description="Maximum speed multiplier")

        # For uniform output type
        min_value: float = Field(0.0, description="Minimum output value")
        max_value: float = Field(1.0, description="Maximum output value")

        # For binary output type
        density: float = Field(0.5, ge=0.0, le=1.0, description="Probability of 1 (for binary type)")

        topic: str | None = Field(None, description="Optional topic override")

    outputs = PortGroup(out=PortSpec(accepts="array"))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._channels = config.output_channels
        self._seed = config.seed
        self._output_type = config.output_type
        self._min_speed = config.min_speed
        self._max_speed = config.max_speed
        self._min_value = config.min_value
        self._max_value = config.max_value
        self._density = config.density
        self._fps = int(config.fps) if config.fps else 30
        self._topic = config.topic or f"random.{self.id}"

        # Pre-generate the random values (they're stable, so we only need to do this once)
        self._values = self._generate_values()

    def _generate_values(self) -> NDArray[np.float32]:
        """Generate deterministic random values based on seed and output type."""
        rng = np.random.Generator(np.random.PCG64(self._seed))

        if self._output_type == "phase":
            # Phase offsets in [0, 1]
            return rng.uniform(0.0, 1.0, self._channels).astype(np.float32)

        elif self._output_type == "speed":
            # Speed multipliers in [min_speed, max_speed]
            return rng.uniform(
                self._min_speed, self._max_speed, self._channels
            ).astype(np.float32)

        elif self._output_type == "uniform":
            # Uniform values in [min_value, max_value]
            return rng.uniform(
                self._min_value, self._max_value, self._channels
            ).astype(np.float32)

        elif self._output_type == "binary":
            # Binary mask based on density
            return (rng.uniform(0.0, 1.0, self._channels) < self._density).astype(np.float32)

        else:
            return rng.uniform(0.0, 1.0, self._channels).astype(np.float32)

    async def start(self, ctx: NodeContext) -> None:
        ctx.start_background(self._run_loop, ctx)

    async def _run_loop(self, ctx: NodeContext) -> None:
        interval = 1.0 / float(self._fps)

        while True:
            now = time.monotonic()

            frame = Frame(
                topic=self._topic,
                timestamp=now,
                payload=ArrayPayload(self._values.copy()),
                metadata=dict(self._metadata),
            )
            await ctx.emit("out", frame)
            await anyio.sleep(interval)

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        pass  # Source nodes don't receive frames

    async def stop(self, ctx: NodeContext) -> None:
        pass
