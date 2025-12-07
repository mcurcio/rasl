"""Channel mapping types for the RASL processing DAG.

This module provides types for representing channel-level connections
between node ports, including overlap detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


class ChannelOverlapError(Exception):
    """Error raised when destination channels overlap.

    Attributes:
        message: Description of the overlap.
        dest_node: The destination node ID.
        dest_port: The destination port name.
        dest_channel: The overlapping channel index.
        existing_source: The existing source (node, port, channel).
        new_source: The new source attempting to connect.
    """

    def __init__(
        self,
        dest_node: str,
        dest_port: str,
        dest_channel: int,
        existing_source: Tuple[str, str, int],
        new_source: Tuple[str, str, int],
    ) -> None:
        self.dest_node = dest_node
        self.dest_port = dest_port
        self.dest_channel = dest_channel
        self.existing_source = existing_source
        self.new_source = new_source

        existing = f"{existing_source[0]}.{existing_source[1]}[{existing_source[2]}]"
        new = f"{new_source[0]}.{new_source[1]}[{new_source[2]}]"
        message = (
            f"Overlap: {dest_node}.{dest_port}[{dest_channel}] already "
            f"receives from {existing}, cannot also receive from {new}"
        )
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ChannelMapping:
    """Maps a contiguous range of source channels to destination channels.

    Attributes:
        source_node: ID of the source node.
        source_port: Name of the source output port.
        source_start: Starting channel index on source (inclusive).
        dest_port: Name of the destination input port.
        dest_start: Starting channel index on destination (inclusive).
        length: Number of channels in this mapping.
    """

    source_node: str
    source_port: str
    source_start: int
    dest_port: str
    dest_start: int
    length: int

    @property
    def source_end(self) -> int:
        """Ending channel index on source (exclusive)."""
        return self.source_start + self.length

    @property
    def dest_end(self) -> int:
        """Ending channel index on destination (exclusive)."""
        return self.dest_start + self.length

    def source_channels(self) -> range:
        """Return the source channel indices covered."""
        return range(self.source_start, self.source_end)

    def dest_channels(self) -> range:
        """Return the destination channel indices covered."""
        return range(self.dest_start, self.dest_end)


class PortChannelRegistry:
    """Tracks channel assignments to detect overlaps.

    Each destination channel can only receive from one source channel.
    This registry tracks all assignments and raises ChannelOverlapError
    if a duplicate assignment is attempted.
    """

    def __init__(self) -> None:
        # Key: (dest_node, dest_port, dest_channel)
        # Value: (source_node, source_port, source_channel)
        self._assignments: Dict[Tuple[str, str, int], Tuple[str, str, int]] = {}

    def assign(
        self,
        dest_node: str,
        dest_port: str,
        dest_channel: int,
        source_node: str,
        source_port: str,
        source_channel: int,
    ) -> None:
        """Record a channel assignment.

        Args:
            dest_node: ID of the destination node.
            dest_port: Name of the destination input port.
            dest_channel: Channel index on the destination port.
            source_node: ID of the source node.
            source_port: Name of the source output port.
            source_channel: Channel index on the source port.

        Raises:
            ChannelOverlapError: If the destination channel is already assigned.
        """
        key = (dest_node, dest_port, dest_channel)
        new_source = (source_node, source_port, source_channel)

        if key in self._assignments:
            existing = self._assignments[key]
            raise ChannelOverlapError(
                dest_node=dest_node,
                dest_port=dest_port,
                dest_channel=dest_channel,
                existing_source=existing,
                new_source=new_source,
            )

        self._assignments[key] = new_source

    def assign_mapping(self, dest_node: str, mapping: ChannelMapping) -> None:
        """Record all channel assignments from a mapping.

        Args:
            dest_node: ID of the destination node.
            mapping: The channel mapping to register.

        Raises:
            ChannelOverlapError: If any destination channel is already assigned.
        """
        for i in range(mapping.length):
            self.assign(
                dest_node=dest_node,
                dest_port=mapping.dest_port,
                dest_channel=mapping.dest_start + i,
                source_node=mapping.source_node,
                source_port=mapping.source_port,
                source_channel=mapping.source_start + i,
            )

    def clear(self) -> None:
        """Clear all recorded assignments."""
        self._assignments.clear()

    def __len__(self) -> int:
        """Return the number of channel assignments."""
        return len(self._assignments)
