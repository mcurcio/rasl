from __future__ import annotations

from typing import Any, Optional, Tuple

import numpy as np

from rasl.engine.frame import Frame
from rasl.engine.node import NodeContext
from rasl.engine.node_config import NodeKind, SinkNodeConfig


class ConsoleSinkNode:
    """Sink node that logs incoming frames to the process logger.

    ConsoleSinkNode is a diagnostic sink that prints channel values and
    optional metadata using the structured logger attached to the node.
    It never emits frames (``outputs == ()``).

    The node is configured via :class:`~rasl.engine.node_config.SinkNodeConfig`,
    usually created by the config loader from a block like:

        rasl {
            node ConsoleSink console {
                input dmx;
                max_channels 24;
                as_bytes true;
                every_n 5;
                include_metadata true;
                label "virtual";
            }
        }

    The loader maps ``input`` to ``config.input.port`` and stores the remaining
    options (``max_channels``, ``as_bytes``, ``every_n``, ``include_metadata``,
    ``label``) in ``config.params``.
    """
    outputs: Tuple[str, ...] = ()

    def __init__(self, config: SinkNodeConfig) -> None:
        if config.kind is not NodeKind.SINK:
            raise ValueError("ConsoleSinkNode requires a sink node config")

        self.id = config.id
        self._config = config

        input_cfg = config.input
        if input_cfg is None:
            raise ValueError("ConsoleSinkNode requires an input port configuration")
        self.inputs: Tuple[str, ...] = (input_cfg.port,)
        self._input_port = input_cfg.port

        max_channels = int(config.params.get("max_channels", input_cfg.channels))
        self._max_channels = max_channels if max_channels > 0 else 0
        self._as_bytes = bool(config.params.get("as_bytes", True))
        every_n = int(config.params.get("every_n", 1))
        self._every_n = every_n if every_n > 0 else 1
        self._include_metadata = bool(config.params.get("include_metadata", True))
        self._label = config.params.get("label")
        self._counter = 0

    async def start(self, ctx: NodeContext) -> None:
        return

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
            "console_frame",
            label=label,
            topic=frame.topic,
            length=len(frame.payload),
            metadata=metadata,
            channels=values,
        )

    async def stop(self, ctx: NodeContext) -> None:
        return
