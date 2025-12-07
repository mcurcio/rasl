"""Port typing system for the RASL processing DAG.

This module provides PortSpec and PortGroup for declaring typed
input/output ports on nodes. The type system enables compile-time
validation of graph connections and channel-level routing.

Payload types are referenced by string name (e.g., "array", "color")
rather than direct class references, enabling a plugin architecture
where the port system is decoupled from specific implementations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional, Tuple, Type, Union


AcceptsSpec = Union[str, Tuple[str, ...]]
"""Type alias for port type constraints.

Can be a single payload type name (e.g., "array") or a tuple of names
(e.g., ("array", "color")) for ports that accept multiple types.
"""

ChannelSpec = Union[int, Tuple[int], Tuple[int, int], None]
"""Channel count specification.

- int: Fixed channel count (e.g., 512)
- (min,): Variable with minimum only (e.g., (0,) for unbounded)
- (min, max): Variable with bounds (e.g., (0, 512))
- None: Variable with no bounds (equivalent to (0,))
"""


def _parse_channel_spec(
    spec: ChannelSpec,
) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """Parse a channel specification into (fixed, min, max).

    Returns:
        Tuple of (fixed_count, min_channels, max_channels).
        If fixed_count is not None, min/max are None.
        If fixed_count is None, this is a variable-length port.
    """
    if spec is None:
        # Variable, no bounds
        return (None, 0, None)
    if isinstance(spec, int):
        # Fixed count
        if spec < 0:
            raise ValueError(f"Channel count must be non-negative, got {spec}")
        return (spec, None, None)
    if isinstance(spec, tuple):
        if len(spec) == 1:
            # (min,) - variable with minimum only
            min_ch = spec[0]
            if not isinstance(min_ch, int) or min_ch < 0:
                raise ValueError(f"Minimum channels must be non-negative int, got {min_ch}")
            return (None, min_ch, None)
        if len(spec) == 2:
            # (min, max) - variable with bounds
            min_ch, max_ch = spec
            if not isinstance(min_ch, int) or min_ch < 0:
                raise ValueError(f"Minimum channels must be non-negative int, got {min_ch}")
            if not isinstance(max_ch, int) or max_ch < 0:
                raise ValueError(f"Maximum channels must be non-negative int, got {max_ch}")
            if max_ch < min_ch:
                raise ValueError(
                    f"Maximum channels ({max_ch}) must be >= minimum ({min_ch})"
                )
            return (None, min_ch, max_ch)
        raise ValueError(
            f"Channel tuple must have 1 or 2 elements, got {len(spec)}"
        )
    raise ValueError(f"Invalid channel spec type: {type(spec).__name__}")


@dataclass(frozen=True, slots=True)
class PortSpec:
    """Specification for a single port's type and channel constraints.

    Attributes:
        accepts: The payload type name(s) this port accepts. Can be a single
            string (e.g., "array") or a tuple of strings (e.g., ("array", "color")).
            Type names are resolved via the payload registry at validation time.
        channels: Channel count specification:
            - int: Fixed channel count (e.g., 512)
            - (min,): Variable with minimum only
            - (min, max): Variable with bounds
            - None: Variable with no bounds (default)
        description: Optional human-readable description of the port.

    Examples:
        >>> PortSpec(accepts="array", channels=512)  # Fixed 512 channels
        >>> PortSpec(accepts="array", channels=(0,))  # Variable, no minimum
        >>> PortSpec(accepts="array", channels=(3,))  # Variable, at least 3
        >>> PortSpec(accepts=("array", "color"))  # Accepts either type
        >>> PortSpec(accepts="array")  # Variable channels, no bounds (default)
    """

    accepts: AcceptsSpec
    channels: ChannelSpec = None
    description: str = ""

    def __post_init__(self) -> None:
        """Validate channel specification on construction."""
        # Validate by parsing (will raise on invalid spec)
        _parse_channel_spec(self.channels)

    @property
    def accepted_types(self) -> tuple[str, ...]:
        """Return tuple of accepted payload type names.
        
        Handles both string-based accepts (new style) and class-based
        accepts (legacy) for backwards compatibility.
        """
        if isinstance(self.accepts, str):
            return (self.accepts,)
        if isinstance(self.accepts, tuple):
            # Could be tuple of strings or tuple of classes
            if self.accepts and isinstance(self.accepts[0], str):
                return self.accepts
            # Tuple of classes - convert to domain names
            return tuple(
                getattr(cls, "domain", cls.__name__) for cls in self.accepts
            )
        # Single class - convert to domain name
        return (getattr(self.accepts, "domain", self.accepts.__name__),)

    def resolve_payload_types(self) -> tuple[Type, ...]:
        """Resolve accepted type names to actual payload classes.

        Returns:
            Tuple of payload classes for the accepted type names.
            For class-based accepts (legacy), returns the classes directly.
            Unknown type names are silently skipped.
        """
        # Handle class-based accepts (legacy)
        if not isinstance(self.accepts, str):
            if isinstance(self.accepts, tuple):
                if self.accepts and not isinstance(self.accepts[0], str):
                    return self.accepts  # Already classes
            elif not isinstance(self.accepts, str):
                return (self.accepts,)  # Single class

        # String-based accepts - resolve via registry
        from .registry import get_payload_type

        types: list[Type] = []
        for name in self.accepted_types:
            payload_cls = get_payload_type(name)
            if payload_cls is not None:
                types.append(payload_cls)
        return tuple(types)

    @property
    def is_variable(self) -> bool:
        """True if this port has variable channel count."""
        fixed, _, _ = _parse_channel_spec(self.channels)
        return fixed is None

    @property
    def fixed_channels(self) -> Optional[int]:
        """Return fixed channel count, or None if variable."""
        fixed, _, _ = _parse_channel_spec(self.channels)
        return fixed

    @property
    def min_channels(self) -> int:
        """Return minimum channel count (0 if no minimum specified)."""
        fixed, min_ch, _ = _parse_channel_spec(self.channels)
        if fixed is not None:
            return fixed
        return min_ch if min_ch is not None else 0

    @property
    def max_channels(self) -> Optional[int]:
        """Return maximum channel count, or None if unbounded."""
        fixed, _, max_ch = _parse_channel_spec(self.channels)
        if fixed is not None:
            return fixed
        return max_ch

    def channel_count(self) -> Optional[int]:
        """Return fixed channel count, or None if variable.

        Alias for fixed_channels for API compatibility.
        """
        return self.fixed_channels

    def validate_index(self, index: int) -> bool:
        """Check if a channel index is valid for this port.

        Args:
            index: 0-based channel index to validate.

        Returns:
            True if the index is valid, False otherwise.
        """
        if index < 0:
            return False
        fixed, _, max_ch = _parse_channel_spec(self.channels)
        if fixed is not None:
            return index < fixed
        if max_ch is not None:
            return index < max_ch
        # Variable with no max: any non-negative index is valid
        return True

    def validate_range(self, start: int, end: int) -> bool:
        """Check if a channel range [start, end) is valid for this port.

        Args:
            start: Starting channel index (inclusive).
            end: Ending channel index (exclusive).

        Returns:
            True if the range is valid, False otherwise.
        """
        if start < 0 or end < start:
            return False
        if end == start:
            return True  # Empty range is valid
        # Check the last channel (end - 1)
        return self.validate_index(end - 1)

    def accepts_payload_type(self, payload_type: Type) -> bool:
        """Check if this port accepts the given payload type.

        Resolves accepted type names to classes and checks if the
        given payload type is compatible with any of them.

        Args:
            payload_type: The type of payload being connected.

        Returns:
            True if the connection is valid, False otherwise.
        """
        resolved_types = self.resolve_payload_types()
        if not resolved_types:
            # No types resolved - accept anything
            return True

        for accept_type in resolved_types:
            # Check if accept_type has is_compatible_with method
            if hasattr(accept_type, "is_compatible_with"):
                if accept_type.is_compatible_with(payload_type):
                    return True
            elif issubclass(payload_type, accept_type):
                return True

        return False


class _EmptyPortGroup:
    """Singleton representing an empty port group.

    Used for source nodes (no inputs) and sink nodes (no outputs)
    when the node doesn't declare the corresponding attribute.
    """

    __slots__ = ()

    def __iter__(self) -> Iterator[str]:
        return iter(())

    def __len__(self) -> int:
        return 0

    def __contains__(self, name: str) -> bool:
        return False

    def get(self, name: str) -> None:
        return None

    def get_default(self) -> tuple[str, PortSpec]:
        raise ValueError("Empty port group has no default")

    @property
    def names(self) -> tuple[str, ...]:
        return ()


EMPTY_PORTS = _EmptyPortGroup()
"""Singleton empty port group for nodes without inputs or outputs."""


class PortGroup:
    """Named collection of ports with default resolution.

    PortGroup provides a dict-like interface for accessing port specs
    by name, with support for default port resolution when there's
    exactly one port in the group.

    Example:
        >>> outputs = PortGroup(
        ...     dmx=PortSpec(accepts=ArrayPayload),
        ... )
        >>> outputs.dmx  # Access by attribute
        PortSpec(accepts=ArrayPayload)
        >>> outputs.get_default()  # Single port is default
        ('dmx', PortSpec(accepts=ArrayPayload))
    """

    __slots__ = ("_ports",)

    def __init__(self, **ports: PortSpec) -> None:
        """Initialize a port group with named port specs.

        Args:
            **ports: Named PortSpec instances.
        """
        self._ports: dict[str, PortSpec] = ports

    def __getattr__(self, name: str) -> PortSpec:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._ports:
            raise AttributeError(f"No port named '{name}'")
        return self._ports[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._ports)

    def __len__(self) -> int:
        return len(self._ports)

    def __contains__(self, name: str) -> bool:
        return name in self._ports

    def get(self, name: str) -> Optional[PortSpec]:
        """Get a port spec by name, or None if not found."""
        return self._ports.get(name)

    def get_default(self) -> tuple[str, PortSpec]:
        """Return (name, spec) for the default port.

        A port is default if and only if it's the sole port in the group.

        Returns:
            Tuple of (port_name, port_spec).

        Raises:
            ValueError: If the group has zero or more than one port.
        """
        if len(self._ports) == 1:
            name = next(iter(self._ports))
            return (name, self._ports[name])
        raise ValueError(
            f"No default port: group has {len(self._ports)} ports"
        )

    @property
    def names(self) -> tuple[str, ...]:
        """Return tuple of all port names in this group."""
        return tuple(self._ports.keys())
