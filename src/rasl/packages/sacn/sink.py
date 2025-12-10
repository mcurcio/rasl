"""sACN/E1.31 sink node for sending DMX universe data.

This module provides SacnSinkNode, which transmits DMX channel data
as sACN (E1.31) packets to network devices (LED controllers, etc.).
It handles rate limiting to respect minimum packet intervals.
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np
import sacn
from pydantic import Field

from rasl.engine.base_node import BaseNode
from rasl.engine.frame import Frame
from rasl.engine.node import NodeContext
from rasl.engine.ports import PortGroup, PortSpec
from rasl.engine.registry import node
from rasl.nodes.models import SinkNodeConfig

from .shims import allow_sacn_universe_zero

# Apply universe 0 patch at module load
allow_sacn_universe_zero()


@node("SacnSinkNode", "SacnSink")
class SacnSinkNode(BaseNode):
    """Sink node that transmits DMX data via sACN (E1.31) protocol.

    SacnSinkNode receives normalized channel data from upstream nodes
    and transmits it as sACN packets to the configured target host
    and universe. It respects minimum packet intervals to avoid
    overwhelming receivers.

    Example config:
        rasl {
            node SacnSink sacnSink0 {
                input_port universe0;
                target_host "10.0.60.30";
                target_universe 0;
                min_interval_ms 25;
                source_name "RASL";
                priority 100;
            }
        }
    """

    class Config(SinkNodeConfig):
        """Configuration for SacnSinkNode."""

        input_port: str = Field("input", description="Input port name")
        target_host: str = Field(..., description="Target IP address (required)")
        target_universe: int = Field(0, ge=0, le=63999, description="sACN universe number")
        min_interval_ms: int = Field(25, ge=0, le=1000, description="Minimum ms between packets")
        source_name: str = Field("RASL", max_length=64, description="sACN source name")
        priority: int = Field(100, ge=0, le=200, description="sACN priority")
        bind_address: str = Field("0.0.0.0", description="Local bind address")
        bind_port: int = Field(0, ge=0, le=65535, description="Local bind port (0=auto)")

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._config = config
        self._input_port = config.input_port

        # Build dynamic input port
        self.inputs = PortGroup.inputs(**{self._input_port: PortSpec(accepts="array")})

        # Strongly-typed config access
        self._target_host = config.target_host
        self._target_universe = config.target_universe
        self._min_interval_ms = config.min_interval_ms
        self._source_name = config.source_name
        self._priority = config.priority
        self._bind_address = config.bind_address
        self._bind_port = config.bind_port

        self._sender: Optional[sacn.sACNsender] = None
        self._last_send_time: float = 0.0

    async def start(self, ctx: NodeContext) -> None:
        fps = 40 if self._min_interval_ms <= 0 else max(1, int(1000 / self._min_interval_ms))
        self._sender = sacn.sACNsender(
            source_name=self._source_name,
            bind_address=self._bind_address,
            bind_port=self._bind_port,
            fps=fps,
        )
        self._sender.start()
        self._sender.activate_output(self._target_universe)
        self._sender[self._target_universe].destination = self._target_host
        self._sender[self._target_universe].priority = self._priority

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        if port != self._input_port or self._sender is None:
            return

        now = time.monotonic()
        elapsed_ms = (now - self._last_send_time) * 1000
        if elapsed_ms < self._min_interval_ms:
            return

        dmx_data = (np.clip(frame.payload, 0.0, 1.0) * 255.0).astype(np.uint8)
        if len(dmx_data) < 512:
            padded = np.zeros(512, dtype=np.uint8)
            padded[: len(dmx_data)] = dmx_data
            dmx_data = padded
        elif len(dmx_data) > 512:
            dmx_data = dmx_data[:512]

        self._sender[self._target_universe].dmx_data = tuple(dmx_data.tolist())
        self._last_send_time = now

    async def stop(self, ctx: NodeContext) -> None:
        if self._sender is not None:
            try:
                self._sender.deactivate_output(self._target_universe)
            except Exception:
                pass
            try:
                self._sender.stop()
            finally:
                self._sender = None
