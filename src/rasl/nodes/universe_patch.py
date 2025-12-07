"""Universe patch transform for remapping DMX channels.

This module provides UniversePatchTransform, which copies segments of
DMX channel data from source universes into a consolidated output buffer.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from rasl.config.models import TransformNodeConfig
from rasl.engine.base_node import BaseNode
from rasl.engine.frame import ArrayPayload, Frame
from rasl.engine.node import NodeContext
from rasl.engine.ports import PortGroup, PortSpec
from rasl.engine.registry import node


class SegmentConfig(BaseModel):
    """Configuration for a single channel mapping segment.

    A Segment specifies how to copy a contiguous range of channels from
    a source universe into a position in the output buffer. Channel
    numbers are 1-indexed (DMX convention).
    """

    source_universe: int = Field(1, ge=0, description="Universe number to copy from")
    source_channel: int = Field(1, ge=1, le=512, description="Starting channel in source")
    length: int = Field(512, ge=1, le=512, description="Number of channels to copy")
    target_channel: int = Field(1, ge=1, description="Starting channel in output buffer")

    @property
    def source_slice(self) -> slice:
        """Compute the slice for reading from source payload."""
        start = self.source_channel - 1
        end = start + self.length
        return slice(start, end)

    @property
    def target_slice(self) -> slice:
        """Compute the slice for writing to target buffer."""
        start = self.target_channel - 1
        end = start + self.length
        return slice(start, end)


@node("UniversePatchTransform", "UniversePatch")
class UniversePatchTransform(BaseNode):
    """Transform node that remaps DMX channels from source universes.

    UniversePatchTransform maintains an internal buffer and copies
    channel segments from incoming frames based on configured Segment
    mappings. When any segment is modified, it emits the complete
    buffer as a new Frame.

    Example config:
        rasl {
            node UniversePatch universePatch0 {
                output_port universe0;
                defaults {
                    source_universe 2;
                    source_channel 1;
                    length 150;
                }
                segment { target_channel 1; }
                segment { target_channel 151; }
            }
        }
    """

    class Config(TransformNodeConfig):
        """Configuration for UniversePatchTransform."""

        input_port: str = Field("dmx", description="Input port name")
        output_port: str = Field("output", description="Output port name")
        segments: list[SegmentConfig] = Field(..., min_length=1, description="Channel mapping segments")
        defaults: SegmentConfig | None = Field(None, description="Default values for segments")

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._config = config
        self._input_port = config.input_port
        self._output_port = config.output_port

        # Apply defaults to segments
        defaults = config.defaults
        self._segments: list[SegmentConfig] = []
        for seg in config.segments:
            if defaults:
                # Merge defaults with segment (explicit segment values take precedence)
                merged = SegmentConfig(
                    source_universe=seg.source_universe if seg.source_universe != 1 else defaults.source_universe,
                    source_channel=seg.source_channel if seg.source_channel != 1 else defaults.source_channel,
                    length=seg.length if seg.length != 512 else defaults.length,
                    target_channel=seg.target_channel,
                )
                self._segments.append(merged)
            else:
                self._segments.append(seg)

        # Compute buffer size
        self._buffer_length = max(
            seg.target_channel - 1 + seg.length for seg in self._segments
        )
        self._buffer = np.zeros(self._buffer_length, dtype=np.float32)

        # Index segments by universe for fast lookup
        self._segments_by_universe: dict[int, list[SegmentConfig]] = {}
        for segment in self._segments:
            self._segments_by_universe.setdefault(segment.source_universe, []).append(segment)

        # Build ports
        self.inputs = PortGroup(**{self._input_port: PortSpec(accepts="array")})
        self.outputs = PortGroup(**{self._output_port: PortSpec(accepts="array")})

    async def start(self, ctx: NodeContext) -> None:
        pass

    async def handle(self, port: str, frame: Frame, ctx: NodeContext) -> None:
        if port != self._input_port:
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
            topic=f"{self.id}.{self._output_port}",
            timestamp=frame.timestamp,
            payload=ArrayPayload(self._buffer.copy()),
            metadata=metadata,
        )
        await ctx.emit(self._output_port, output_frame)

    async def stop(self, ctx: NodeContext) -> None:
        pass
