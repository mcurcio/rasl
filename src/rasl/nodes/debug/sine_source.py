"""Sine wave test source node.

This module provides SineSourceNode, a virtual source useful for testing
graphs without hardware. It generates a sine wave pattern and emits it
as normalized Frames at a configurable frame rate.
"""

from __future__ import annotations

import math
import time

import anyio
import numpy as np
from pydantic import Field

from rasl.graph.node import BaseNode, NodeContext, SourceNodeConfig, node
from rasl.graph.ports import OutputPortSpec, PortGroup
from rasl.signal import Frame, MatrixPayload


@node("SineSourceNode", "SineSource")
class SineSourceNode(BaseNode):
    """Source node that generates a test sine waveform.

    SineSourceNode is a virtual source useful for testing graphs without
    hardware. It fills a buffer with a single scalar sine value and emits
    it on the "dmx" output port at a fixed frame rate.

    Example config:
        graph {
            node SineSource sine {
                output_channels 512;
                frequency_hz 1.0;
                fps 30;
                amplitude 0.5;
                offset 0.5;
            }
        }
    """

    class Config(SourceNodeConfig):
        """Configuration for SineSourceNode."""

        output_channels: int = Field(512, ge=1, le=65536, description="Number of output channels")
        frequency_hz: float = Field(1.0, ge=0.001, le=100.0, description="Sine frequency in Hz")
        amplitude: float = Field(0.5, ge=0.0, le=1.0, description="Wave amplitude")
        offset: float = Field(0.5, ge=0.0, le=1.0, description="DC offset")
        topic: str | None = Field(None, description="Optional topic override")

    outputs = PortGroup.outputs(dmx=OutputPortSpec(MatrixPayload))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._config = config
        self._channels = config.output_channels
        # The element count is fixed by config (rasl-00l)
        self.outputs = PortGroup.outputs(
            dmx=OutputPortSpec(MatrixPayload, count=config.output_channels, components=1)
        )
        self._frequency_hz = config.frequency_hz
        self._amplitude = config.amplitude
        self._offset = config.offset
        self._fps = int(config.fps.hz) if config.fps else 30
        self._topic = config.topic or f"sine.{self.id}"

    async def start(self, ctx: NodeContext) -> None:
        """Start the background task that writes a frame to ``dmx`` every ``1 / fps`` seconds."""
        ctx.start_background(self._run_loop, ctx)

    async def _run_loop(self, ctx: NodeContext) -> None:
        interval = 1.0 / float(self._fps)
        t0 = time.monotonic()
        while True:
            now = time.monotonic()
            t = now - t0
            phase = 2.0 * math.pi * self._frequency_hz * t
            value = self._offset + self._amplitude * math.sin(phase)
            out_port = self.outputs.dmx
            buf = out_port.acquire(self._channels)
            payload = np.asarray(buf, dtype=np.float32)
            payload[: self._channels, 0] = float(value)
            np.clip(payload, 0.0, 1.0, out=payload)
            frame = Frame(
                topic=self._topic,
                timestamp=now,
                payload=MatrixPayload(payload[: self._channels, :1]),
                metadata=self._metadata,
            )
            out_port.commit(frame)
            await anyio.sleep(interval)

    async def stop(self, ctx: NodeContext) -> None:
        """Do nothing: the node context cancels the background task."""
        pass
