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

import anyio
from pydantic import Field, field_validator

from rasl.config.units import parse_interval
from rasl.engine.base_node import BaseNode
from rasl.engine.frame import Frame, FramePayload
from rasl.engine.node import NodeContext
from rasl.engine.ports import PortGroup, PortSpec
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
        self.inputs = PortGroup.inputs(**{self._input_port: PortSpec(accepts="array")})

        # Strongly-typed config access
        self._target = config.target
        self._interval_s = config.get_interval_s()
        self._fps = 1.0 / self._interval_s

        self._client: Optional[DDPClient] = None
        self._ctx: Optional[NodeContext] = None
        
        # Background worker state
        self._pending_payload: Optional[FramePayload] = None
        self._payload_lock = threading.Lock()
        self._send_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._shutdown = False
        
        # Stats
        self._frames_sent = 0
        self._frames_dropped = 0

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
                payload = self._pending_payload
                self._pending_payload = None
            
            if payload is None:
                continue
            
            # Send it
            try:
                send_start = time.perf_counter()
                if self._client:
                    self._client.send(payload)
                send_ms = (time.perf_counter() - send_start) * 1000
                self._frames_sent += 1
                
                # Log warning if DDP send takes too long
                if send_ms > 10.0 and self._ctx:
                    self._ctx.logger.warning(
                        event="ddp_send_slow",
                        target=self._target,
                        send_ms=round(send_ms, 2),
                        payload_bytes=len(payload.data) if hasattr(payload, 'data') else 0,
                    )
            except OSError as e:
                if self._ctx:
                    self._ctx.logger.error(
                        event="ddp_send_error",
                        target=self._target,
                        error=str(e),
                    )

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

        # Queue for background send (non-blocking)
        with self._payload_lock:
            if self._pending_payload is not None:
                # Previous frame wasn't sent yet - dropping it
                self._frames_dropped += 1
            self._pending_payload = frame.payload
        
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
