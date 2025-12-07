"""DDP (Distributed Display Protocol) sink node for LED pixel data.

This module provides DdpSinkNode, which transmits RGB pixel data
as DDP packets to network devices (LED controllers, WLED, etc.).
DDP is optimized for high pixel counts with up to 480 RGB pixels per packet.

Protocol reference: http://www.3waylabs.com/ddp/
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np
from pydantic import Field, field_validator

from rasl.config.models import SinkNodeConfig
from rasl.config.units import parse_interval
from rasl.engine.base_node import BaseNode
from rasl.engine.ddp import DDPClient
from rasl.engine.frame import Frame
from rasl.engine.node import NodeContext
from rasl.engine.ports import PortGroup, PortSpec
from rasl.engine.registry import node


@node("DdpSinkNode", "DdpSink")
class DdpSinkNode(BaseNode):
    """Sink node that transmits RGB pixel data via DDP protocol.

    DdpSinkNode receives normalized RGB channel data from upstream nodes
    and transmits it as DDP packets to the configured target host.
    DDP supports up to 480 RGB pixels per packet, making it efficient
    for large LED installations.

    The input port is dynamically named based on the `input_port` config,
    allowing flexible connection syntax in config files.

    Example config:
        rasl {
            node DdpSink leds {
                target "10.0.60.30";
                fps 20hz;      # or "20", "50ms"
                input_port pixels;

                connect toRgb[0:151] pixels;
            }
        }

    Attributes:
        inputs: Dynamic PortGroup with single input port.
    """

    class Config(SinkNodeConfig):
        """Configuration for DdpSinkNode."""

        input_port: str = Field("input", description="Input port name")
        target: str = Field(..., description="Target IP address (required)")
        fps: str = Field("20hz", description="Frame rate (e.g., '30hz', '20', '50ms')")

        # Computed field for interval in seconds
        _interval_s: float = 0.05

        @field_validator("fps")
        @classmethod
        def validate_fps(cls, v: str) -> str:
            """Validate fps can be parsed as interval."""
            interval = parse_interval(v)
            if interval <= 0:
                raise ValueError("fps must result in positive interval")
            if interval < 0.001:  # > 1000 fps
                raise ValueError("fps too high (max ~1000hz)")
            return v

        def get_interval_s(self) -> float:
            """Get the interval in seconds."""
            return parse_interval(self.fps)

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._config = config
        self._input_port = config.input_port

        # Build dynamic input port
        self.inputs = PortGroup(**{self._input_port: PortSpec(accepts="array")})

        # Strongly-typed config access
        self._target = config.target
        self._interval_s = config.get_interval_s()

        self._client: Optional[DDPClient] = None
        self._last_send_time: float = 0.0

    async def start(self, ctx: NodeContext) -> None:
        """Initialize DDP client."""
        self._client = DDPClient(self._target)
        self._client.connect()
        ctx.logger.info(
            event="ddp_sink_started",
            target=self._target,
            interval_ms=self._interval_s * 1000,
            input_port=self._input_port,
        )

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        """Process incoming frame and send as DDP packets."""
        if port != self._input_port or self._client is None:
            return

        # Rate limiting
        now = time.monotonic()
        elapsed = now - self._last_send_time
        if elapsed < self._interval_s:
            return

        try:
            self._client.send(frame.payload)
        except OSError as e:
            ctx.logger.error(
                event="ddp_send_error",
                target=self._target,
                error=str(e),
            )
            return

        self._last_send_time = now

    async def stop(self, ctx: NodeContext) -> None:
        """Close DDP client."""
        if self._client is not None:
            self._client.close()
            self._client = None
            ctx.logger.info(event="ddp_sink_stopped", target=self._target)
