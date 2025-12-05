"""Universe patch transform for remapping DMX channels.

This module provides UniversePatchTransform, which copies segments of
DMX channel data from source universes into a consolidated output buffer.
This enables remapping channels from multiple source universes into a
single output universe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np

from rasl.engine.frame import Frame
from rasl.engine.node import Node, NodeContext
from rasl.engine.node_config import NodeKind, TransformNodeConfig


@dataclass(frozen=True, slots=True)
class Segment:
    """Defines a mapping from source channels to target buffer positions.

    A Segment specifies how to copy a contiguous range of channels from
    a source universe into a position in the output buffer. Channel
    numbers are 1-indexed (DMX convention).

    Attributes:
        source_universe: Universe number to copy from (1-63999).
        source_channel: Starting channel in source universe (1-512).
        length: Number of channels to copy.
        target_channel: Starting channel in output buffer (1-indexed).

    Example:
        >>> segment = Segment(
        ...     source_universe=1,
        ...     source_channel=1,
        ...     length=150,
        ...     target_channel=1
        ... )
        >>> # Copies channels 1-150 from universe 1 to output positions 1-150
    """

    source_universe: int
    """Universe number to copy channels from (1-63999)."""

    source_channel: int
    """Starting channel in the source universe (1-indexed, 1-512)."""

    length: int
    """Number of channels to copy from source to target."""

    target_channel: int
    """Starting channel position in the output buffer (1-indexed)."""

    @property
    def source_slice(self) -> slice:
        """Compute the slice for reading from source payload.

        Converts from 1-indexed DMX channels to 0-indexed array indices.

        Returns:
            slice object for indexing the source frame payload.
        """
        start = self.source_channel - 1
        end = start + self.length
        return slice(start, end)

    @property
    def target_slice(self) -> slice:
        """Compute the slice for writing to target buffer.

        Converts from 1-indexed DMX channels to 0-indexed array indices.

        Returns:
            slice object for indexing the output buffer.
        """
        start = self.target_channel - 1
        end = start + self.length
        return slice(start, end)


class UniversePatchTransform:
    """Transform node that remaps DMX channels from source universes.

    UniversePatchTransform maintains an internal buffer and copies
    channel segments from incoming frames based on configured Segment
    mappings. When any segment is modified, it emits the complete
    buffer as a new Frame.

    This is analogous to the NormalizedInputSegment logic in the
    TypeScript implementation (src/config/loader.ts).

    Attributes:
        id: Unique node identifier.
        inputs: Tuple containing "dmx" input port.
        outputs: Tuple containing the configured output port name.

    The node is configured via :class:`~rasl.engine.node_config.TransformNodeConfig`,
    usually created by the config loader from a block like:

        rasl {
            node UniversePatch universePatch0 {
                output universe0;
                defaults {
                    source_universe 2;
                    source_channel 1;
                    length 150;
                }
                segment { target_channel 1; }
                segment { target_channel 151; }
                segment { target_channel 301; }
                segment { length 62; target_channel 451; }
            }
        }

    The loader parses each ``segment { ... }`` block into a :class:`Segment` and
    stores the resulting list in ``config.params["segments"]``. It also sets:

    * ``input`` to a :class:`PortIOConfig` for the ``"dmx"`` input.
    * ``output`` to a :class:`PortIOConfig` sized to the maximum target channel.

    Attributes:
        id: Unique node identifier.
        inputs: Tuple containing "dmx" input port.
        outputs: Tuple containing the configured output port name.
    """

    inputs: Tuple[str, ...] = ("dmx",)
    """Input port names. Accepts DMX frames on 'dmx' port."""

    def __init__(self, config: TransformNodeConfig) -> None:
        """Initialize the universe patch transform.

        Args:
            config: Typed configuration for this transform node.

        Raises:
            ValueError: If segments list is empty.
        """
        if config.kind is not NodeKind.TRANSFORM:
            raise ValueError("UniversePatchTransform requires a transform node config")

        segments_param = config.params.get("segments")
        segments: List[Segment] = list(segments_param or [])
        if not segments:
            raise ValueError("UniversePatchTransform requires at least one segment")
        self.id = config.id
        self._config = config

        output_cfg = config.output
        output_port = output_cfg.port if output_cfg is not None else "output"
        self.outputs: Tuple[str, ...] = (output_port,)
        self._segments: List[Segment] = segments
        self._buffer_length: int = max(
            seg.target_channel - 1 + seg.length for seg in segments
        )
        self._buffer: np.ndarray = np.zeros(self._buffer_length, dtype=np.float32)
        self._segments_by_universe: Dict[int, List[Segment]] = {}
        for segment in segments:
            self._segments_by_universe.setdefault(segment.source_universe, []).append(
                segment
            )

    async def start(self, ctx: NodeContext) -> None:
        """Initialize the transform (no-op).

        Args:
            ctx: Node execution context.
        """
        pass

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        """Process an incoming DMX frame and emit patched output.

        Copies channel data from the frame into the internal buffer
        according to the configured segments. If any data was copied,
        emits the complete buffer as a new Frame.

        Args:
            port: Input port name (must be "dmx").
            frame: Incoming Frame with DMX channel data.
            ctx: Node execution context for emitting output.
        """
        if port != "dmx":
            return
        universe: Any = frame.metadata.get("sourceUniverse")
        if universe is None:
            return
        segments = self._segments_by_universe.get(int(universe))
        if not segments:
            return
        modified = False
        for segment in segments:
            payload_slice = frame.payload[segment.source_slice]
            if payload_slice.size == 0:
                continue
            target_slice = segment.target_slice
            copy_length = min(payload_slice.size, self._buffer[target_slice].size)
            self._buffer[target_slice][:copy_length] = payload_slice[:copy_length]
            modified = True
        if not modified:
            return
        metadata = dict(frame.metadata)
        metadata["bufferId"] = self.id
        output_frame = Frame(
            topic=f"{self.id}.{self.outputs[0]}",
            timestamp=frame.timestamp,
            payload=self._buffer.copy(),
            metadata=metadata,
        )
        await ctx.emit(self.outputs[0], output_frame)

    async def stop(self, ctx: NodeContext) -> None:
        """Clean up the transform (no-op).

        Args:
            ctx: Node execution context.
        """
        pass
