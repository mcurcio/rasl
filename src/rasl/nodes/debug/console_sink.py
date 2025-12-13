"""Console sink node for debugging and logging.

This module provides ConsoleSinkNode, which logs incoming frame data
and metadata to the structured logger. Useful for debugging graphs
without hardware.

Pull-based: This is a rate-driving sink that uses @pull_rate to
drive the scheduler at the configured fps.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from pydantic import Field

from rasl.engine.nodes import BaseNode, NodeContext
from rasl.engine.frames import ColorPayload, Frame, MatrixPayload
from rasl.engine.ports import InputPortSpec, PortGroup
from rasl.engine.registry import node
from rasl.engine.tick import TickContext, pull_rate
from rasl.nodes.models import SinkNodeConfig


@node("ConsoleSinkNode", "ConsoleSink")
class ConsoleSinkNode(BaseNode):
    """Sink node that logs frame data to the console.

    ConsoleSinkNode is useful for debugging graphs without hardware.
    It logs incoming frame data and metadata to the structured logger
    at configurable intervals.

    Pull-based: Uses @pull_rate to drive the scheduler.

    Example config:
        rasl {
            node ConsoleSink debug {
                input_port data;
                max_channels 16;
                fps 30;  # Drive scheduler at 30 Hz
                as_bytes true;
                include_metadata true;
                label "Debug Output";
            }
        }
    """

    class Config(SinkNodeConfig):
        """Configuration for ConsoleSinkNode."""

        input_port: str = Field("dmx", description="Input port name")
        max_channels: int = Field(16, ge=1, le=512, description="Max channels to display")
        as_bytes: bool = Field(True, description="Display as 0-255 bytes instead of 0.0-1.0")
        fps: float = Field(30.0, ge=1.0, le=120.0, description="Frame rate to drive scheduler")
        include_metadata: bool = Field(True, description="Include frame metadata in log")
        label: str | None = Field(None, description="Optional label for log output")

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._config = config
        self._input_port = config.input_port

        # Build dynamic input port
        self.inputs = PortGroup.inputs(
            **{self._input_port: InputPortSpec((MatrixPayload, ColorPayload))}
        )

        self._max_channels = config.max_channels
        self._as_bytes = config.as_bytes
        self._fps = config.fps
        self._include_metadata = config.include_metadata
        self._label = config.label or self.id

        self._counter = 0
        self._ctx: Optional[NodeContext] = None

    async def start(self, ctx: NodeContext) -> None:
        self._ctx = ctx
        ctx.logger.info(
            event="console_sink_started",
            label=self._label,
            input_port=self._input_port,
            max_channels=self._max_channels,
            fps=self._fps,
        )

    @pull_rate(lambda self: self._fps)
    async def pull(self, tick: TickContext) -> None:
        """Pull upstream and log frame data."""
        if self._ctx is None:
            return

        # Read from the dynamic input port
        port = self.inputs.get(self._input_port)
        if port is None:
            return

        frame = port.read()
        if frame is None:
            return

        self._counter += 1
        log_data = {
            "event": "console_sink_frame",
            "label": self._label,
            "frame_count": self._counter,
            "tick": tick.tick,
            "t": round(tick.t, 3),
            "data": frame.payload,
        }

        if self._include_metadata and frame.metadata:
            log_data["metadata"] = dict(frame.metadata)

        self._ctx.logger.info(**log_data)

    async def stop(self, ctx: NodeContext) -> None:
        ctx.logger.info(
            event="console_sink_stopped",
            label=self._label,
            total_frames=self._counter,
        )
