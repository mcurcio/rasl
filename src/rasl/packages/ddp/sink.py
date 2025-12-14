"""DDP (Distributed Display Protocol) sink node for LED pixel data.

This module provides DdpSinkNode, which transmits RGB pixel data
as DDP packets to network devices (LED controllers, WLED, etc.).
DDP is optimized for high pixel counts with up to 480 RGB pixels per packet.

Pull-based: This is a rate-driving sink that uses @pull_rate to
drive the scheduler at the configured fps.

Protocol reference: http://www.3waylabs.com/ddp/
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import zlib

import numpy as np
from pydantic import Field, field_validator

from rasl.config.units import parse_interval
from rasl.engine.nodes import BaseNode, NodeContext
from rasl.engine.frames import ColorPayload, Frame, FramePayload, MatrixPayload
from rasl.engine.ports import InputPortSpec, PortGroup
from rasl.engine.registry import node
from rasl.engine.tick import TickContext, pull_rate
from rasl.nodes.models import SinkNodeConfig

from .client import DDPClient

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
        max_count: int | None = Field(
            None,
            ge=1,
            description="Maximum number of elements to send (e.g. pixels).",
        )
        push_every_packet: bool = Field(
            False,
            description="Send DDP_PUSH flag on every packet (instead of only the last packet).",
        )

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
        self.inputs = PortGroup.inputs(
            **{self._input_port: InputPortSpec((MatrixPayload, ColorPayload))}
        )

        # Strongly-typed config access
        self._target = config.target
        self._interval_s = config.get_interval_s()
        self._fps = 1.0 / self._interval_s
        self._max_count = config.max_count
        self._push_every_packet = bool(config.push_every_packet)

        self._client: Optional[DDPClient] = None
        self._ctx: Optional[NodeContext] = None
        
        # Stats
        self._frames_sent = 0
        self._frames_dropped = 0

        # Diagnostics
        self._prev_checksum: int | None = None
        self._prev_byte_data: np.ndarray | None = None
        self._last_diag_log_t: float = 0.0

    async def start(self, ctx: NodeContext) -> None:
        """Initialize DDP client."""
        self._ctx = ctx
        self._client = DDPClient(self._target)
        self._client.connect(blocking=False)
        
        ctx.logger.info(
            event="ddp_sink_started",
            target=self._target,
            fps=self._fps,
            input_port=self._input_port,
        )

    def _run_diagnostics(
        self,
        send_data: Any,
        payload_count: int | None,
        payload_channels: int | None,
    ) -> None:
        if self._ctx is None:
            return

        now = time.perf_counter()
        should_log = (now - self._last_diag_log_t) >= 1.0

        arr = np.asarray(send_data)
        if arr.size == 0:
            return

        if np.issubdtype(arr.dtype, np.floating):
            finite = np.isfinite(arr)
            non_finite = int(arr.size - int(finite.sum()))
            min_val = float(np.nanmin(arr))
            max_val = float(np.nanmax(arr))
            clipped = np.clip(arr, 0.0, 1.0)
            byte_data = (clipped * 255.0).astype(np.uint8)
            below0 = int((arr < 0.0).sum())
            above1 = int((arr > 1.0).sum())
        else:
            non_finite = 0
            min_val = float(arr.min())
            max_val = float(arr.max())
            if arr.dtype == np.uint8:
                byte_data = arr
            else:
                byte_data = arr.astype(np.uint8)
            below0 = 0
            above1 = 0

        byte_data = byte_data.ravel()
        if byte_data.size == 0:
            return

        checksum = zlib.crc32(memoryview(byte_data)) & 0xFFFFFFFF
        white_bytes = int((byte_data == 255).sum())
        zero_bytes = int((byte_data == 0).sum())
        white_ratio = white_bytes / float(byte_data.size)

        delta_mean: float | None = None
        if self._prev_byte_data is not None and self._prev_byte_data.size == byte_data.size:
            delta = np.abs(byte_data.astype(np.int16) - self._prev_byte_data.astype(np.int16))
            delta_mean = float(delta.mean())

        suspicious = False
        if non_finite > 0:
            suspicious = True
        if below0 > 0 or above1 > 0:
            suspicious = True
        if white_ratio > 0.90:
            suspicious = True
        if delta_mean is not None and delta_mean > 40.0:
            suspicious = True

        if suspicious or should_log:
            self._ctx.logger.info(
                event="ddp_frame_diag",
                target=self._target,
                bytes=int(byte_data.size),
                checksum=int(checksum),
                prev_checksum=int(self._prev_checksum) if self._prev_checksum is not None else None,
                count=payload_count,
                channels=payload_channels,
                min=round(min_val, 6),
                max=round(max_val, 6),
                non_finite=int(non_finite),
                below0=int(below0),
                above1=int(above1),
                white_ratio=round(white_ratio, 4),
                zero_ratio=round(zero_bytes / float(byte_data.size), 4),
                delta_mean=round(delta_mean, 4) if delta_mean is not None else None,
                suspicious=bool(suspicious),
            )
            self._last_diag_log_t = now

        self._prev_checksum = checksum
        self._prev_byte_data = byte_data

    @pull_rate(lambda self: self._fps)
    async def pull(self, tick: TickContext) -> None:
        """Pull upstream and send data via non-blocking UDP.
        """
        if self._client is None:
            return

        # Read from the dynamic input port
        port = self.inputs.get(self._input_port)
        if port is None:
            return

        frame = port.read()
        if frame is None:
            return

        payload: FramePayload = frame.payload

        data_obj: Any
        if hasattr(payload, "flatten"):
            data_obj = payload.flatten()
        else:
            data_obj = payload

        arr = np.asarray(data_obj)
        if arr.ndim != 1:
            arr = arr.ravel()

        if np.issubdtype(arr.dtype, np.floating):
            byte_data = (np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8)
        else:
            byte_data = arr.astype(np.uint8)

        payload_count = getattr(payload, "count", None)
        payload_channels = getattr(payload, "channels", None)

        if self._max_count is not None and payload_channels is not None:
            max_len = int(self._max_count) * int(payload_channels)
            if max_len > 0 and byte_data.size > max_len:
                byte_data = byte_data[:max_len]

        byte_data = np.ascontiguousarray(byte_data).ravel()
        if byte_data.size == 0:
            return

        try:
            send_start = time.perf_counter()
            self._run_diagnostics(byte_data, payload_count, payload_channels)
            next_offset = self._client.send_nonblocking(
                byte_data,
                start_offset=0,
                push_every_packet=bool(self._push_every_packet),
            )
            send_ms = (time.perf_counter() - send_start) * 1000

            if next_offset == 0:
                self._frames_sent += 1
            else:
                # Could not send the full frame this tick.
                self._frames_dropped += 1

            if send_ms > 10.0 and self._ctx:
                self._ctx.logger.warning(
                    event="ddp_send_slow",
                    target=self._target,
                    send_ms=round(send_ms, 2),
                    payload_bytes=int(byte_data.size),
                    next_offset=int(next_offset),
                )
        except OSError as e:
            if self._ctx:
                self._ctx.logger.error(
                    event="ddp_send_error",
                    target=self._target,
                    error=str(e),
                )

    async def stop(self, ctx: NodeContext) -> None:
        """Close DDP client."""
        if self._client is not None:
            self._client.close()
            self._client = None
        
        ctx.logger.info(
            event="ddp_sink_stopped",
            target=self._target,
            frames_sent=self._frames_sent,
            frames_dropped=self._frames_dropped,
        )
