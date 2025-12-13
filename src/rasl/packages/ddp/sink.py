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
import threading
import time
from typing import Any, Optional

import zlib

import anyio
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

        self._client: Optional[DDPClient] = None
        self._ctx: Optional[NodeContext] = None
        
        # Background worker state
        self._pending_frame: Optional[tuple[np.ndarray, int | None, int | None]] = None
        self._payload_lock = threading.Lock()
        self._send_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._shutdown = False
        
        # Stats
        self._frames_sent = 0
        self._frames_dropped = 0

        # Diagnostics
        self._prev_checksum: int | None = None
        self._prev_byte_data: np.ndarray | None = None
        self._last_diag_log_t: float = 0.0

    async def start(self, ctx: NodeContext) -> None:
        """Initialize DDP client and start background worker."""
        self._ctx = ctx
        self._client = DDPClient(self._target)
        self._client.connect()
        
        # Start background send worker
        self._shutdown = False
        self._worker_thread = threading.Thread(
            target=self._send_worker,
            name=f"ddp-send-{self._target}",
            daemon=True,
        )
        self._worker_thread.start()
        
        ctx.logger.info(
            event="ddp_sink_started",
            target=self._target,
            fps=self._fps,
            input_port=self._input_port,
        )

    def _send_worker(self) -> None:
        """Background worker that sends the latest frame.
        
        This runs in a dedicated thread to avoid blocking the async event loop.
        If a new frame arrives while sending, the old pending frame is dropped
        (natural backpressure for slow networks).
        """
        while not self._shutdown:
            # Wait for a frame to send
            if not self._send_event.wait(timeout=0.1):
                continue
            
            self._send_event.clear()
            
            # Grab the pending payload
            with self._payload_lock:
                pending = self._pending_frame
                self._pending_frame = None
            
            if pending is None:
                continue

            send_data, payload_count, payload_channels = pending
            
            # Send it
            try:
                send_start = time.perf_counter()
                if self._client:
                    self._run_diagnostics(send_data, payload_count, payload_channels)
                    self._client.send(send_data)
                send_ms = (time.perf_counter() - send_start) * 1000
                self._frames_sent += 1
                
                # Log warning if DDP send takes too long
                if send_ms > 10.0 and self._ctx:
                    self._ctx.logger.warning(
                        event="ddp_send_slow",
                        target=self._target,
                        send_ms=round(send_ms, 2),
                        payload_bytes=int(np.asarray(send_data).size),
                    )
            except OSError as e:
                if self._ctx:
                    self._ctx.logger.error(
                        event="ddp_send_error",
                        target=self._target,
                        error=str(e),
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
        """Pull upstream and queue frame for background send.
        
        This method never blocks on network I/O. It simply updates the
        pending payload and signals the background worker. If the worker
        is still sending the previous frame, this frame will replace it
        (frame dropping for backpressure).
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

        # Queue for background send (non-blocking)
        with self._payload_lock:
            if self._pending_frame is not None:
                # Previous frame wasn't sent yet - dropping it
                self._frames_dropped += 1
            self._pending_frame = (byte_data, payload_count, payload_channels)
        
        # Signal the worker
        self._send_event.set()

    async def stop(self, ctx: NodeContext) -> None:
        """Stop background worker and close DDP client."""
        # Signal shutdown
        self._shutdown = True
        self._send_event.set()  # Wake worker to exit
        
        # Wait for worker to finish
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=1.0)
            self._worker_thread = None
        
        if self._client is not None:
            self._client.close()
            self._client = None
        
        ctx.logger.info(
            event="ddp_sink_stopped",
            target=self._target,
            frames_sent=self._frames_sent,
            frames_dropped=self._frames_dropped,
        )
