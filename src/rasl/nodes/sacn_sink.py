"""sACN/E1.31 sink node for sending DMX universe data.

This module provides SacnSinkNode, which transmits DMX channel data
as sACN (E1.31) packets to network devices (LED controllers, etc.).
It handles rate limiting to respect minimum packet intervals.
"""

from __future__ import annotations

import time
from typing import Any, Optional, Tuple

import numpy as np
import sacn

from rasl.engine.frame import Frame
from rasl.engine.node import Node, NodeContext
from rasl.engine.node_config import NodeKind, SinkNodeConfig
from rasl.shims import allow_sacn_universe_zero

allow_sacn_universe_zero()


class SacnSinkNode:
    """Sink node that transmits DMX data via sACN (E1.31) protocol.

    SacnSinkNode receives normalized channel data from upstream nodes
    and transmits it as sACN packets to the configured target host
    and universe. It respects minimum packet intervals to avoid
    overwhelming receivers.

    This is a SinkNode (no outputs) that accepts frames on a configurable
    input port.

    Attributes:
        id: Unique node identifier.
        inputs: Tuple containing the configured input port name.
        outputs: Empty tuple (sink node has no outputs).

    The node is configured via :class:`~rasl.engine.node_config.SinkNodeConfig`,
    typically created by the config loader from a block like:

        rasl {
            node SacnSink sacnSink0 {
                input universe0;
                target_host "10.0.60.30";
                target_universe 0;
                min_interval_ms 25;
                source_name "RASL";
                priority 100;
            }
        }

    The loader builds a SinkNodeConfig where:

    * ``input.port`` is taken from ``input`` (``universe0`` in the example).
    * ``params["target_host"]`` / ``params["target_universe"]`` select the target.
    * ``params["min_interval_ms"]`` controls rate limiting.
    * ``params["source_name"]`` and ``params["priority"]`` configure sACN metadata.

    Attributes:
        id: Unique node identifier.
        inputs: Tuple containing the configured input port name.
        outputs: Empty tuple (sink node has no outputs).
    """

    outputs: Tuple[str, ...] = ()
    """Empty tuple - sink nodes do not emit output frames."""

    def __init__(self, config: SinkNodeConfig) -> None:
        """Initialize the sACN sink node.

        Args:
            config: Typed configuration for this sACN sink node.
        """
        if config.kind is not NodeKind.SINK:
            raise ValueError("SacnSinkNode requires a sink node config")

        self.id = config.id
        self._config = config

        input_cfg = config.input
        if input_cfg is None:
            raise ValueError("SacnSinkNode requires an input port configuration")
        self.inputs: Tuple[str, ...] = (input_cfg.port,)
        self._input_port: str = input_cfg.port

        params = config.params
        self._target_host = str(params["target_host"])
        self._target_universe = int(params.get("target_universe", 0))
        self._min_interval_ms = int(params.get("min_interval_ms", 25))
        self._source_name = str(params.get("source_name", "RASL"))
        self._priority = int(params.get("priority", 100))
        self._bind_address = str(params.get("bind_address", "0.0.0.0"))
        self._bind_port = int(params.get("bind_port", 0))
        self._sender: Optional[sacn.sACNsender] = None
        self._last_send_time: float = 0.0
        self._sequence: int = 0

    def _next_sequence(self) -> int:
        """Get the next sequence number for sACN packets.

        Sequence numbers wrap from 255 to 0 (skipping 0 per E1.31 spec
        uses 0 for sync, but library may handle this).

        Returns:
            Next sequence number (0-255).
        """
        seq = self._sequence
        self._sequence = (self._sequence + 1) % 256
        return seq

    async def start(self, ctx: NodeContext) -> None:
        """Start the sACN sender and activate the output.

        Called by the Runtime when execution begins. Sets up the sACN
        sender with the configured target.

        Args:
            ctx: Node execution context providing runtime services.
        """
        # sACN sender requires fps > 0. Derive from min interval (ms) or use
        # a safe default when unrestricted.
        fps = 40 if self._min_interval_ms <= 0 else max(1, int(1000 / self._min_interval_ms))

        self._sender = sacn.sACNsender(
            source_name=self._source_name,
            bind_address=self._bind_address,
            bind_port=self._bind_port,
            fps=fps,
        )
        self._sender.start()  # type: ignore[no-untyped-call]
        # Activate the universe for unicast to target host
        self._sender.activate_output(self._target_universe)  # type: ignore[no-untyped-call]
        self._sender[self._target_universe].destination = self._target_host
        self._sender[self._target_universe].priority = self._priority

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        """Process an incoming frame and transmit via sACN.

        Converts the normalized float32 channel data back to DMX bytes
        (0-255) and transmits if the minimum interval has elapsed.

        Args:
            port: Input port name (must match configured input_port).
            frame: Incoming Frame with normalized channel data.
            ctx: Node execution context.
        """
        if port != self._input_port:
            return
        if self._sender is None:
            return

        # Rate limiting
        now = time.monotonic()
        elapsed_ms = (now - self._last_send_time) * 1000
        if elapsed_ms < self._min_interval_ms:
            return

        # Convert normalized float32 [0.0, 1.0] back to DMX bytes [0, 255]
        dmx_data = (np.clip(frame.payload, 0.0, 1.0) * 255.0).astype(np.uint8)

        # Ensure we have exactly 512 channels (pad or truncate)
        if len(dmx_data) < 512:
            padded = np.zeros(512, dtype=np.uint8)
            padded[: len(dmx_data)] = dmx_data
            dmx_data = padded
        elif len(dmx_data) > 512:
            dmx_data = dmx_data[:512]

        # Send the packet
        self._sender[self._target_universe].dmx_data = tuple(dmx_data.tolist())
        self._last_send_time = now

    async def stop(self, ctx: NodeContext) -> None:
        """Stop the sACN sender and release resources.

        Called by the Runtime during graceful shutdown. Deactivates
        the output and stops the sender.

        Args:
            ctx: Node execution context.
        """
        if self._sender is not None:
            try:
                self._sender.deactivate_output(self._target_universe)  # type: ignore[no-untyped-call]
            except Exception:
                pass  # Ignore errors during shutdown
            try:
                self._sender.stop()  # type: ignore[no-untyped-call]
            finally:
                self._sender = None
