"""sACN/E1.31 sink node for sending DMX universe data.

This module provides SacnSinkNode, which transmits DMX channel data
as sACN (E1.31) packets to network devices (LED controllers, etc.).
It handles rate limiting to respect minimum packet intervals.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import sacn
from pydantic import Field

from rasl.engine.frames import MatrixPayload
from rasl.engine.nodes import BaseNode, NodeContext
from rasl.engine.nodes.config import SinkNodeConfig
from rasl.engine.ports import InputPortSpec, PortGroup
from rasl.engine.registry import node
from rasl.engine.tick import TickContext, pull_rate
from rasl.packages.sacn.shims import allow_sacn_universe_zero

# Apply universe 0 patch at module load
allow_sacn_universe_zero()


@node("SacnSinkNode", "SacnSink")
class SacnSinkNode(BaseNode):
    """Sink node that transmits DMX data via sACN (E1.31) protocol.

    SacnSinkNode receives normalized channel data from upstream nodes
    and transmits it as sACN packets to the configured target host
    and universe. It is a rate-driving sink: it pulls its input and sends
    one packet every ``min_interval_ms`` (40 a second when that is 0).

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

        # The input port carries the configured name
        self.inputs = PortGroup.inputs(**{self._input_port: InputPortSpec(MatrixPayload)})

        # Strongly-typed config access
        self._target_host = config.target_host
        self._target_universe = config.target_universe
        self._min_interval_ms = config.min_interval_ms
        self._source_name = config.source_name
        self._priority = config.priority
        self._bind_address = config.bind_address
        self._bind_port = config.bind_port

        # Packets per second: as many as min_interval_ms allows (40 when it is 0)
        self._fps = 40 if self._min_interval_ms <= 0 else max(1, int(1000 / self._min_interval_ms))

        self._sender: Optional[sacn.sACNsender] = None

    async def start(self, ctx: NodeContext) -> None:
        self._sender = sacn.sACNsender(
            source_name=self._source_name,
            bind_address=self._bind_address,
            bind_port=self._bind_port,
            fps=self._fps,
        )
        self._sender.start()
        self._sender.activate_output(self._target_universe)
        self._sender[self._target_universe].destination = self._target_host
        self._sender[self._target_universe].priority = self._priority

    @pull_rate(lambda self: self._fps)
    async def pull(self, tick: TickContext) -> None:
        """Send the input's latest frame as one universe of DMX."""
        if self._sender is None:
            return
        frame = self.inputs.get(self._input_port).read()
        if frame is None:
            return

        # Rows in order, each row's components in order: RGB pixels become R, G, B, R, ...
        values = np.asarray(frame.payload, dtype=np.float32).reshape(-1)
        dmx_data = (np.clip(values, 0.0, 1.0) * 255.0).astype(np.uint8)
        if len(dmx_data) < 512:
            padded = np.zeros(512, dtype=np.uint8)
            padded[: len(dmx_data)] = dmx_data
            dmx_data = padded
        elif len(dmx_data) > 512:
            dmx_data = dmx_data[:512]

        self._sender[self._target_universe].dmx_data = tuple(dmx_data.tolist())

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
