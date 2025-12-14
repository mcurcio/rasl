"""SeededRandom source node.

Produces deterministic per-channel random values based on a seed.

This is useful for effects like twinkle where each pixel needs a stable
random phase offset or speed multiplier.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import Field

from rasl.engine.frames import Frame, MatrixPayload
from rasl.engine.nodes import BaseNode
from rasl.engine.ports import OutputPortSpec, PortGroup
from rasl.engine.registry import node
from rasl.engine.tick import TickContext
from rasl.nodes.models import SourceNodeConfig


SeededOutputType = Literal["phase", "speed", "uniform", "binary"]


@node("SeededRandomNode", "SeededRandom")
class SeededRandomNode(BaseNode):
    class Config(SourceNodeConfig):
        seed: int = Field(42, description="Random seed")
        output_channels: int = Field(512, ge=1, le=65536, description="Number of output channels")
        output_type: SeededOutputType = Field(
            "uniform",
            description="Output type: phase (0..1), speed (min..max), uniform (0..1), binary (0/1)",
        )
        min_value: float = Field(0.0, ge=0.0, le=1.0, description="Minimum value (for output_type=uniform)")
        max_value: float = Field(1.0, ge=0.0, le=1.0, description="Maximum value (for output_type=uniform)")
        min_speed: float = Field(1.0, ge=0.0, description="Minimum speed (for output_type=speed)")
        max_speed: float = Field(3.0, ge=0.0, description="Maximum speed (for output_type=speed)")
        density: float = Field(0.1, ge=0.0, le=1.0, description="Probability of 1 (for output_type=binary)")
        topic: str | None = Field(None, description="Optional topic override")

    outputs = PortGroup.outputs(out=OutputPortSpec(MatrixPayload))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._channels = config.output_channels
        self._topic = config.topic or f"seeded_random.{self.id}"

        rng = np.random.Generator(np.random.PCG64(config.seed))

        output_type = config.output_type
        if output_type == "phase":
            values = rng.random(self._channels, dtype=np.float32)
        elif output_type == "uniform":
            lo = float(config.min_value)
            hi = float(config.max_value)
            if hi < lo:
                lo, hi = hi, lo
            values = (rng.random(self._channels, dtype=np.float32) * (hi - lo) + lo).astype(np.float32)
        elif output_type == "speed":
            lo = float(config.min_speed)
            hi = float(config.max_speed)
            if hi < lo:
                lo, hi = hi, lo
            values = (rng.random(self._channels, dtype=np.float32) * (hi - lo) + lo).astype(np.float32)
        else:  # binary
            values = (rng.random(self._channels, dtype=np.float32) < float(config.density)).astype(np.float32)

        self._values = values

    async def pull(self, tick: TickContext) -> None:
        out_port = self.outputs.out
        buf = out_port.acquire(self._channels)
        arr = np.asarray(buf, dtype=np.float32)
        arr[: self._channels, 0] = self._values

        out_port.commit(
            Frame(
                topic=self._topic,
                timestamp=tick.wall_time,
                payload=MatrixPayload(arr[: self._channels, :1]),
                metadata=self._metadata,
            )
        )
