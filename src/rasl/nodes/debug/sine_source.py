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

from rasl.engine.base_node import BaseNode
from rasl.engine.frame import ArrayPayload, Frame
from rasl.engine.node import NodeContext
from rasl.engine.ports import PortGroup, PortSpec
from rasl.engine.registry import node
from rasl.nodes.models import SourceNodeConfig


@node("SineSourceNode", "SineSource")
class SineSourceNode(BaseNode):
    """Source node that generates a test sine waveform.

    SineSourceNode is a virtual source useful for testing graphs without
    hardware. It fills a buffer with a single scalar sine value and emits
    it on the "dmx" output port at a fixed frame rate.

    Example config:
        rasl {
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

    outputs = PortGroup.outputs(dmx=PortSpec(accepts="array"))

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._config = config
        self._channels = config.output_channels
        self._frequency_hz = config.frequency_hz
        self._amplitude = config.amplitude
        self._offset = config.offset
        self._fps = int(config.fps) if config.fps else 30
        self._topic = config.topic or f"sine.{self.id}"

    async def start(self, ctx: NodeContext) -> None:
        ctx.start_background(self._run_loop, ctx)

    async def _run_loop(self, ctx: NodeContext) -> None:
        interval = 1.0 / float(self._fps)
        t0 = time.monotonic()
        while True:
            now = time.monotonic()
            t = now - t0
            phase = 2.0 * math.pi * self._frequency_hz * t
            value = self._offset + self._amplitude * math.sin(phase)
            payload = np.full(self._channels, value, dtype=np.float32)
            payload = np.clip(payload, 0.0, 1.0)
            frame = Frame(
                topic=self._topic,
                timestamp=now,
                payload=ArrayPayload(payload),
                metadata=dict(self._metadata),
            )
            await ctx.emit("dmx", frame)
            await anyio.sleep(interval)

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        pass  # Source nodes don't receive frames

    async def stop(self, ctx: NodeContext) -> None:
        pass
