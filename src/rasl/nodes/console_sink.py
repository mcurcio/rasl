"""Console sink node for logging frame data.

This module provides ConsoleSinkNode, a diagnostic sink that prints
channel values and optional metadata using the structured logger.
"""

from __future__ import annotations

import numpy as np
from pydantic import Field

from rasl.config.models import SinkNodeConfig
from rasl.engine.base_node import BaseNode
from rasl.engine.frame import Frame
from rasl.engine.node import NodeContext
from rasl.engine.ports import PortGroup, PortSpec
from rasl.engine.registry import node


@node("ConsoleSinkNode", "ConsoleSink")
class ConsoleSinkNode(BaseNode):
    """Sink node that logs incoming frames to the process logger.

    ConsoleSinkNode is a diagnostic sink that prints channel values and
    optional metadata using the structured logger attached to the node.

    Example config:
        rasl {
            node ConsoleSink console {
                input_port dmx;
                max_channels 24;
                as_bytes true;
                every_n 5;
                include_metadata true;
                label "virtual";
            }
        }
    """

    class Config(SinkNodeConfig):
        """Configuration for ConsoleSinkNode."""

        input_port: str = Field("input", description="Input port name")
        max_channels: int = Field(16, ge=0, description="Maximum channels to display (0=all)")
        as_bytes: bool = Field(True, description="Display as byte values (0-255) instead of floats")
        every_n: int = Field(1, ge=1, description="Log every Nth frame")
        include_metadata: bool = Field(True, description="Include frame metadata in log")
        label: str | None = Field(None, description="Optional label for log output")

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._config = config
        self._input_port = config.input_port

        # Build dynamic input port
        self.inputs = PortGroup(**{self._input_port: PortSpec(accepts="array")})

        self._max_channels = config.max_channels
        self._as_bytes = config.as_bytes
        self._every_n = config.every_n
        self._include_metadata = config.include_metadata
        self._label = config.label
        self._counter = 0

    async def start(self, ctx: NodeContext) -> None:
        pass

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        if port != self._input_port:
            return
        self._counter += 1
        if self._counter % self._every_n != 0:
            return

        payload = frame.payload
        if self._as_bytes:
            payload = (np.clip(payload, 0.0, 1.0) * 255.0).astype(np.uint8)
        if self._max_channels > 0:
            payload = payload[: self._max_channels]

        values = payload.tolist()
        label = self._label or self.id
        metadata = None
        if self._include_metadata and frame.metadata:
            metadata = dict(frame.metadata)

        ctx.logger.info(
            label=label,
            topic=frame.topic,
            payload_type=type(frame.payload).__name__,
            length=len(frame.payload),
            metadata=metadata,
            channels=values,
        )

    async def stop(self, ctx: NodeContext) -> None:
        pass
