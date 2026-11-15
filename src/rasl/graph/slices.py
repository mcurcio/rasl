"""Slices of a port, as edges carry them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class Slice:
    """A run of a port's elements: ``[start, end)``, as an edge reads or writes it.

    The config's connect syntax produces these; the graph checks and compiles them.

    Attributes:
        start: Starting channel index (inclusive, 0-based).
        end: Ending channel index (exclusive). None = open-ended.
    """

    start: int
    end: Optional[int] = None

    @property
    def is_open(self) -> bool:
        """True if this slice has no explicit end."""
        return self.end is None

    def length(self, port_channels: Optional[int]) -> Optional[int]:
        """Compute length given port's channel count.

        Args:
            port_channels: The port's fixed channel count, or None if variable.

        Returns:
            The number of channels in this slice, or None if both slice
            and port are unbounded.
        """
        if self.end is not None:
            return self.end - self.start
        if port_channels is not None:
            return port_channels - self.start
        return None  # Both open-ended
