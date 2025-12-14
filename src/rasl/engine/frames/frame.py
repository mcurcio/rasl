"""Frame dataclass for the RASL processing DAG.

This module defines the immutable Frame dataclass that represents
a normalized payload flowing through the node graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, MutableMapping

from .base import FramePayload


Metadata = Mapping[str, Any]
"""Type alias for frame metadata dictionaries."""


EMPTY_METADATA: Metadata = MappingProxyType({})


def _empty_metadata() -> Metadata:
    return EMPTY_METADATA


@dataclass(frozen=True, slots=True)
class Frame:
    """Immutable payload flowing through the processing DAG.

    A Frame represents a single unit of data traveling between nodes.
    It contains normalized channel data (float32 values from 0.0 to 1.0),
    a topic for routing, a monotonic timestamp, and arbitrary metadata.

    Frames are immutable (frozen dataclass) to ensure thread-safety
    and prevent unintended side effects during concurrent processing.

    Attributes:
        topic: Routing key identifying the data source or type.
            Convention: "sacn.universe.{n}" for sACN universe data.
        timestamp: Monotonic time (seconds) when the frame was created.
            Use time.monotonic() for consistent timing.
        payload: Normalized channel data as a MatrixFrame or subclass.
            Values are in range [0.0, 1.0]. Source adapters convert
            from raw byte values (0-255); sink adapters reverse this.
        metadata: Arbitrary key-value pairs for frame context.
            Common keys: sourceUniverse, priority, sequence, colorSpace.

    Example:
        >>> import numpy as np
        >>> import time
        >>> from rasl.engine.frames import MatrixPayload
        >>> frame = Frame(
        ...     topic="sacn.universe.1",
        ...     timestamp=time.monotonic(),
        ...     payload=MatrixPayload(np.zeros(512, dtype=np.float32)),
        ...     metadata={"sourceUniverse": 1, "colorSpace": "rgb"}
        ... )
    """

    topic: str
    """Routing key identifying the data source or type."""

    timestamp: float
    """Monotonic timestamp (seconds) when the frame was created."""

    payload: FramePayload
    """Normalized channel data as MatrixFrame with values in [0.0, 1.0]."""

    metadata: Metadata = field(default_factory=_empty_metadata)
    """Arbitrary key-value pairs providing frame context."""

    def with_payload(self, payload: FramePayload) -> Frame:
        """Create a new Frame with a different payload.

        Returns a copy of this frame with the payload replaced.
        The original frame is unchanged.

        Args:
            payload: The new payload for the frame.

        Returns:
            A new Frame instance with the new payload.
        """
        return Frame(
            topic=self.topic,
            timestamp=self.timestamp,
            payload=payload,
            metadata=self.metadata,
        )

    def with_metadata(self, **updates: Any) -> Frame:
        """Create a new Frame with updated metadata.

        Returns a copy of this frame with the specified metadata keys
        added or overwritten. The original frame is unchanged.

        Args:
            **updates: Key-value pairs to add or update in metadata.

        Returns:
            A new Frame instance with merged metadata.

        Example:
            >>> new_frame = frame.with_metadata(processed=True, nodeId="patch1")
        """
        existing: MutableMapping[str, Any] = dict(self.metadata)
        existing.update(updates)
        return Frame(
            topic=self.topic,
            timestamp=self.timestamp,
            payload=self.payload,
            metadata=existing,
        )
