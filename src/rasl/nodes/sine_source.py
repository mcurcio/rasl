from __future__ import annotations

import math
import time
from typing import Any, Iterable, Mapping, Optional, Tuple

import anyio
import numpy as np

from rasl.engine.frame import Frame
from rasl.engine.node import NodeContext
from rasl.engine.node_config import NodeKind, SourceNodeConfig


class SineSourceNode:
    """Source node that generates a test sine waveform.

    SineSourceNode is a virtual source useful for testing graphs without
    hardware. It fills a DMX-shaped buffer with a single scalar sine value
    and emits it on the ``"dmx"`` output port at a fixed frame rate.

    The node is configured via :class:`~rasl.engine.node_config.SourceNodeConfig`,
    typically created by the config loader from a block like:

        rasl {
            node SineSource sine {
                outputs 512;        # number of channels
                frequency_hz 1.0;   # sine frequency in Hz
                fps 30;             # output frame rate
                amplitude 0.5;
                offset 0.5;
                # optional: topic "sine.sine";
                # optional: metadata "colorSpace=rgb";
            }
        }

    The loader maps ``outputs`` to ``config.output.channels`` and stores the
    remaining parameters in ``config.params``.
    """
    inputs: Tuple[str, ...] = ()
    outputs: Tuple[str, ...] = ("dmx",)

    def __init__(self, config: SourceNodeConfig) -> None:
        if config.kind is not NodeKind.SOURCE:
            raise ValueError("SineSourceNode requires a source node config")

        self.id = config.id
        self._config = config

        output_cfg = config.output
        if output_cfg is None:
            raise ValueError("SineSourceNode requires an output port configuration")
        if output_cfg.channels <= 0:
            raise ValueError("SineSourceNode requires channels > 0")
        self._channels = int(output_cfg.channels)

        self._frequency_hz = float(config.params.get("frequency_hz", 1.0))
        fps_value = config.timing.fps
        self._fps = int(fps_value) if fps_value and fps_value > 0 else 30
        self._amplitude = float(config.params.get("amplitude", 0.5))
        self._offset = float(config.params.get("offset", 0.5))
        metadata = config.params.get("metadata")
        self._metadata = dict(metadata or {})
        self._topic = str(config.params.get("topic", f"sine.{self.id}"))

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
            timestamp = now
            metadata: dict[str, Any] = dict(self._metadata)
            frame = Frame(
                topic=self._topic,
                timestamp=timestamp,
                payload=payload,
                metadata=metadata,
            )
            await ctx.emit("dmx", frame)
            await anyio.sleep(interval)

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        return

    async def stop(self, ctx: NodeContext) -> None:
        return
