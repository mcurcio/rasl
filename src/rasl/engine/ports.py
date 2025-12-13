"""Port typing system for the RASL processing DAG.

This module provides PortSpec and PortGroup for declaring typed
input/output ports on nodes. The type system enables compile-time
validation of graph connections and channel-level routing.

Payload types are referenced by string name (e.g., "array", "color")
rather than direct class references, enabling a plugin architecture
where the port system is decoupled from specific implementations.

The port model supports both pull-based and push-based execution:
- InputPort: Read data from upstream nodes via read()
- OutputPort: Write data to downstream nodes via write()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Iterator, Optional, Tuple, Type, Union

if TYPE_CHECKING:
    from .frames import Frame


AcceptsSpec = Union[str, Type, Tuple[str, ...], Tuple[Type, ...]]
"""Type alias for port type constraints.

Can be a single payload type name (e.g., "array") or a tuple of names
(e.g., ("array", "color")) for ports that accept multiple types.
"""

CountSpec = Union[int, Tuple[int], Tuple[int, int], None]
"""Count specification.

- int: Fixed count (e.g., 512)
- (min,): Variable with minimum only (e.g., (0,) for unbounded)
- (min, max): Variable with bounds (e.g., (0, 512))
- None: Variable with no bounds (equivalent to (0,))
"""


def _parse_count_spec(
    spec: CountSpec,
) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """Parse a count specification into (fixed_count, min_count, max_count).

    Returns:
        Tuple of (fixed_count, min_count, max_count).
        If fixed_count is not None, min/max are None.
        If fixed_count is None, this is a variable-length port.
    """
    if spec is None:
        # Variable, no bounds
        return (None, 0, None)
    if isinstance(spec, int):
        # Fixed count
        if spec < 0:
            raise ValueError(f"Count must be non-negative, got {spec}")
        return (spec, None, None)
    if isinstance(spec, tuple):
        if len(spec) == 1:
            # (min,) - variable with minimum only
            min_count = spec[0]
            if not isinstance(min_count, int) or min_count < 0:
                raise ValueError(
                    f"Minimum count must be non-negative int, got {min_count}"
                )
            return (None, min_count, None)
        if len(spec) == 2:
            # (min, max) - variable with bounds
            min_count, max_count = spec
            if not isinstance(min_count, int) or min_count < 0:
                raise ValueError(
                    f"Minimum count must be non-negative int, got {min_count}"
                )
            if not isinstance(max_count, int) or max_count < 0:
                raise ValueError(
                    f"Maximum count must be non-negative int, got {max_count}"
                )
            if max_count < min_count:
                raise ValueError(
                    f"Maximum count ({max_count}) must be >= minimum ({min_count})"
                )
            return (None, min_count, max_count)
        raise ValueError(
            f"Count tuple must have 1 or 2 elements, got {len(spec)}"
        )
    raise ValueError(f"Invalid count spec type: {type(spec).__name__}")


@dataclass(frozen=True, slots=True)
class InputPortSpec:
    """Specification for a single port's type and count constraints.

    Attributes:
        accepts: The payload type name(s) this port accepts. Can be a single
            string (e.g., "array") or a tuple of strings (e.g., ("array", "color")).
            Type names are resolved via the payload registry at validation time.
        count: Count specification:
            - int: Fixed count (e.g., 512)
            - (min,): Variable with minimum only
            - (min, max): Variable with bounds
            - None: Variable with no bounds (default)
        description: Optional human-readable description of the port.

    Examples:
        >>> from rasl.engine.frames import ColorPayload, MatrixPayload
        >>> InputPortSpec(MatrixPayload, count=512)  # Fixed 512 count
        >>> InputPortSpec(MatrixPayload, count=(0,))  # Variable, no minimum
        >>> InputPortSpec(MatrixPayload, count=(3,))  # Variable, at least 3
        >>> InputPortSpec((MatrixPayload, ColorPayload))  # Accepts either type
        >>> InputPortSpec(MatrixPayload)  # Variable count, no bounds (default)
    """

    accepts: AcceptsSpec
    count: CountSpec = None
    description: str = ""

    def __post_init__(self) -> None:
        _parse_count_spec(self.count)

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
        fixed, _, _ = _parse_count_spec(self.count)
        return fixed is None

    @property
    def fixed_count(self) -> Optional[int]:
        fixed, _, _ = _parse_count_spec(self.count)
        return fixed

    @property
    def min_count(self) -> int:
        fixed, min_count, _ = _parse_count_spec(self.count)
        if fixed is not None:
            return fixed
        return min_count if min_count is not None else 0

    @property
    def max_count(self) -> Optional[int]:
        fixed, _, max_count = _parse_count_spec(self.count)
        if fixed is not None:
            return fixed
        return max_count

    def validate_index(self, index: int) -> bool:
        """Check if an index is valid for this port.

        Args:
            index: 0-based channel index to validate.

        Returns:
            True if the index is valid, False otherwise.
        """
        if index < 0:
            return False

        fixed, _, max_count = _parse_count_spec(self.count)
        if fixed is not None:
            return index < fixed
        if max_count is not None:
            return index < max_count
        # Variable with no max: any non-negative index is valid
        return True

    def validate_range(self, start: int, end: int) -> bool:
        """Check if a range [start, end) is valid for this port."""
        if start < 0 or end < start:
            return False
        if end == start:
            return True
        return self.validate_index(end - 1)

    def accepts_payload_type(self, payload_type: Type) -> bool:
        """Check if this port accepts the given payload type."""
        resolved_types = self.resolve_payload_types()
        if not resolved_types:
            return True

        for accept_type in resolved_types:
            if hasattr(accept_type, "is_compatible_with"):
                if accept_type.is_compatible_with(payload_type):
                    return True
            elif issubclass(payload_type, accept_type):
                return True

        return False


ProducesSpec = Union[str, Type]


@dataclass(frozen=True, slots=True)
class OutputPortSpec:
    produces: ProducesSpec
    count: CountSpec = None
    description: str = ""

    def __post_init__(self) -> None:
        _parse_count_spec(self.count)
        if isinstance(self.produces, tuple):
            raise ValueError("OutputPortSpec.produces must be a single type")

    @property
    def type_name(self) -> str:
        if isinstance(self.produces, str):
            return self.produces
        return getattr(self.produces, "domain", self.produces.__name__)

    def resolve_payload_types(self) -> tuple[Type, ...]:
        if not isinstance(self.produces, str):
            return (self.produces,)

        from .registry import get_payload_type

        payload_cls = get_payload_type(self.produces)
        if payload_cls is None:
            return ()
        return (payload_cls,)

    @property
    def is_variable(self) -> bool:
        fixed, _, _ = _parse_count_spec(self.count)
        return fixed is None

    @property
    def fixed_count(self) -> Optional[int]:
        fixed, _, _ = _parse_count_spec(self.count)
        return fixed

    @property
    def min_count(self) -> int:
        fixed, min_count, _ = _parse_count_spec(self.count)
        if fixed is not None:
            return fixed
        return min_count if min_count is not None else 0

    @property
    def max_count(self) -> Optional[int]:
        fixed, _, max_count = _parse_count_spec(self.count)
        if fixed is not None:
            return fixed
        return max_count

    def validate_index(self, index: int) -> bool:
        if index < 0:
            return False
        fixed, _, max_count = _parse_count_spec(self.count)
        if fixed is not None:
            return index < fixed
        if max_count is not None:
            return index < max_count
        return True

    def validate_range(self, start: int, end: int) -> bool:
        if start < 0 or end < start:
            return False
        if end == start:
            return True
        return self.validate_index(end - 1)

    def accepts_payload_type(self, payload_type: Type) -> bool:
        resolved_types = self.resolve_payload_types()
        if not resolved_types:
            return True

        accept_type = resolved_types[0]
        if hasattr(accept_type, "is_compatible_with"):
            return accept_type.is_compatible_with(payload_type)
        return issubclass(payload_type, accept_type)


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

    def get_default(self) -> tuple[str, InputPortSpec | OutputPortSpec]:
        raise ValueError("Empty port group has no default")

    @property
    def names(self) -> tuple[str, ...]:
        return ()


EMPTY_PORTS = _EmptyPortGroup()
"""Singleton empty port group for nodes without inputs or outputs."""


class PortGroup:
    """Named collection of input or output ports.

    PortGroup creates InputPort or OutputPort objects directly as attributes,
    providing fast attribute access without dynamic lookup. Use the factory
    methods `inputs()` and `outputs()` to create port groups.

    Example:
        >>> from rasl.engine.frames import ColorPayload, MatrixPayload
        >>> outputs = PortGroup.outputs(dmx=OutputPortSpec(MatrixPayload))
        >>> outputs.dmx  # Direct attribute access to OutputPort
        OutputPort(name='dmx', ...)
        >>> outputs.dmx.write(frame)  # Write to port
        
        >>> inputs = PortGroup.inputs(color=InputPortSpec(ColorPayload))
        >>> inputs.color.read()  # Read from port
    """

    # Ports are stored as direct attributes for fast access
    # No __slots__ so we can add port attributes dynamically

    @classmethod
    def inputs(cls, **ports: InputPortSpec) -> "PortGroup":
        """Create an input port group.
        
        Args:
            **ports: Named InputPortSpec instances defining input ports.
            
        Returns:
            PortGroup with InputPort objects as attributes.
        """
        return cls(_is_input=True, **ports)

    @classmethod
    def outputs(cls, **ports: OutputPortSpec) -> "PortGroup":
        """Create an output port group.
        
        Args:
            **ports: Named OutputPortSpec instances defining output ports.
            
        Returns:
            PortGroup with OutputPort objects as attributes.
        """
        return cls(_is_input=False, **ports)

    def __init__(self, *, _is_input: bool, **ports: InputPortSpec | OutputPortSpec) -> None:
        """Initialize a port group (use factory methods instead).

        Args:
            _is_input: True for InputPorts, False for OutputPorts.
            **ports: Named InputPortSpec or OutputPortSpec instances.
        """
        object.__setattr__(self, "_port_names", tuple(ports.keys()))
        object.__setattr__(self, "_is_input", _is_input)
        
        # Create port objects directly as attributes
        for name, spec in ports.items():
            if _is_input:
                port = InputPort(name=name, spec=spec)
            else:
                port = OutputPort(name=name, spec=spec)
            object.__setattr__(self, name, port)

    def __iter__(self) -> Iterator["InputPort | OutputPort"]:
        """Iterate over port objects."""
        for name in self._port_names:
            yield getattr(self, name)

    def __len__(self) -> int:
        return len(self._port_names)

    def __contains__(self, name: str) -> bool:
        return name in self._port_names

    def get(self, name: str) -> Optional["InputPort | OutputPort"]:
        """Get a port by name, or None if not found."""
        if name in self._port_names:
            return getattr(self, name)
        return None

    def get_default(self) -> tuple[str, "InputPort | OutputPort"]:
        """Return (name, port) for the default port.

        A port is default if and only if it's the sole port in the group.

        Returns:
            Tuple of (port_name, port_object).

        Raises:
            ValueError: If the group has zero or more than one port.
        """
        if len(self._port_names) == 1:
            name = self._port_names[0]
            return (name, getattr(self, name))
        raise ValueError(
            f"No default port: group has {len(self._port_names)} ports"
        )

    @property
    def names(self) -> tuple[str, ...]:
        """Return tuple of all port names in this group."""
        return self._port_names
    
    @property
    def is_input(self) -> bool:
        """True if this is an input port group."""
        return self._is_input


# =============================================================================
# Runtime Port Objects (used during execution)
# =============================================================================


@dataclass
class InputPort:
    """A readable input port on a node.

    In PULL mode: Contains pre-pulled frame from upstream.
    In PUSH mode: Contains most recently pushed frame.

    Nodes read from input ports via read() during pull() execution.

    Attributes:
        name: Port name within the node.
        spec: InputPortSpec (type constraints, channels).
    """

    name: str
    spec: InputPortSpec
    _frame: Optional["Frame"] = field(default=None, repr=False)
    _has_upstream: bool = field(default=False, repr=False)

    def read(self, default: Optional["Frame"] = None) -> Optional["Frame"]:
        """Read the current frame on this port.

        Args:
            default: Value to return if no frame available.

        Returns:
            The frame, or default if port is empty/unconnected.
        """
        return self._frame if self._frame is not None else default

    @property
    def connected(self) -> bool:
        """True if an upstream node is connected to this port."""
        return self._has_upstream

    @property
    def count(self) -> Optional[int]:
        return self.spec.fixed_count

    def accepts_payload_type(self, payload_type: Type) -> bool:
        """Check if this port accepts a payload type (delegated to spec)."""
        return self.spec.accepts_payload_type(payload_type)

    def resolve_payload_types(self) -> tuple[Type, ...]:
        """Resolve accepted type names to actual payload classes (delegated to spec)."""
        return self.spec.resolve_payload_types()

    def _set_frame(self, frame: Optional["Frame"]) -> None:
        """Internal: Set the frame (called by scheduler)."""
        self._frame = frame

    def _clear(self) -> None:
        """Internal: Clear the frame."""
        self._frame = None


@dataclass
class OutputPort:
    """A writable output port on a node.

    Nodes write frames to output ports during pull() execution.
    The scheduler routes written frames to connected downstream nodes.

    For push sources, writing also triggers a scheduler wakeup so the
    frame can be propagated to downstream nodes.

    Attributes:
        name: Port name within the node.
        spec: OutputPortSpec (type constraints, channels).
    """

    name: str
    spec: OutputPortSpec
    _frame: Optional["Frame"] = field(default=None, repr=False)
    _written: bool = field(default=False, repr=False)
    _front_buffer: object | None = field(default=None, repr=False)
    _back_buffer: object | None = field(default=None, repr=False)
    _node_id: str = field(default="", repr=False)
    _on_write: Optional[Callable[["OutputPort"], None]] = field(default=None, repr=False)

    def write(self, frame: "Frame") -> None:
        """Write a frame to this output port.

        The frame will be routed to all connected downstream nodes
        after the current node's processing completes.

        For push sources, this also triggers a scheduler wakeup.

        Args:
            frame: The frame to output.
        """
        self._frame = frame
        self._written = True
        # Notify scheduler for push sources
        if self._on_write is not None:
            self._on_write(self)

    def acquire(self, count: int, *, components: int | None = None) -> "object":
        """Acquire a writable buffer for the next commit.

        Returns a NumPy array view (shape (count, components)) backed by the
        port's back buffer.
        """
        # Determine component width
        payload_type = None
        resolved = self.spec.resolve_payload_types()
        if resolved:
            payload_type = resolved[0]
            if components is None:
                components = getattr(payload_type, "components", None)

        if components is None:
            components = 1

        if payload_type is None:
            raise ValueError(
                f"OutputPort '{self.name}' cannot acquire a buffer: unresolved payload type '{self.spec.type_name}'"
            )

        # Delegate real storage allocation/resizing to the payload type.
        buf = payload_type.ensure_buffer(
            self._back_buffer,
            count=count,
            components=components,
        )
        self._back_buffer = buf
        return buf[:count, :components]

    def commit(self, frame: "Frame") -> None:
        """Commit a frame that uses the last-acquired back buffer.

        Swaps the port's front/back buffers to guarantee that previously
        committed frames remain stable until the next commit.
        """
        if not self.spec.accepts_payload_type(type(frame.payload)):
            raise TypeError(
                f"OutputPort '{self.name}' does not accept payload type {type(frame.payload).__name__}"
            )

        self._frame = frame
        self._written = True

        # Swap buffers: the just-written back buffer becomes the new front buffer.
        self._front_buffer, self._back_buffer = self._back_buffer, self._front_buffer

        if self._on_write is not None:
            self._on_write(self)

    @property
    def was_written(self) -> bool:
        """True if write() was called since last consume."""
        return self._written

    @property
    def count(self) -> Optional[int]:
        return self.spec.fixed_count

    def accepts_payload_type(self, payload_type: Type) -> bool:
        """Check if this port accepts a payload type (delegated to spec)."""
        return self.spec.accepts_payload_type(payload_type)

    def resolve_payload_types(self) -> tuple[Type, ...]:
        """Resolve accepted type names to actual payload classes (delegated to spec)."""
        return self.spec.resolve_payload_types()

    def _consume(self) -> Optional["Frame"]:
        """Internal: Get written frame and reset state."""
        frame = self._frame
        self._frame = None
        self._written = False
        return frame

    def _clear(self) -> None:
        """Internal: Clear the frame without consuming."""
        self._frame = None
        self._written = False


class BoundPortGroup:
    """Runtime port group with actual InputPort/OutputPort instances.

    Created when a node is instantiated, binding PortSpecs to actual
    port objects that can hold frame data.

    Example:
        # In node's __init__:
        self._bound_inputs = BoundPortGroup.from_specs(self.inputs, is_input=True)

        # In node's pull():
        frame = self._bound_inputs.color.read()
    """

    __slots__ = ("_ports", "_is_input")

    def __init__(self, ports: dict[str, InputPort | OutputPort], is_input: bool) -> None:
        self._ports = ports
        self._is_input = is_input

    @classmethod
    def from_specs(cls, spec_group: PortGroup, is_input: bool) -> "BoundPortGroup":
        """Create bound ports from a PortGroup specification."""
        ports: dict[str, InputPort | OutputPort] = {}
        for name in spec_group.names:
            port = spec_group.get(name)
            if port is None:
                continue
            if is_input:
                if not isinstance(port, InputPort):
                    raise TypeError("Expected InputPort")
                ports[name] = InputPort(name=name, spec=port.spec)
            else:
                if not isinstance(port, OutputPort):
                    raise TypeError("Expected OutputPort")
                ports[name] = OutputPort(name=name, spec=port.spec)
        return cls(ports, is_input)

    def __getattr__(self, name: str) -> InputPort | OutputPort:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._ports:
            raise AttributeError(f"No port named '{name}'")
        return self._ports[name]

    def __iter__(self) -> Iterator[InputPort | OutputPort]:
        return iter(self._ports.values())

    def __contains__(self, name: str) -> bool:
        return name in self._ports

    def __len__(self) -> int:
        return len(self._ports)

    def get(self, name: str) -> Optional[InputPort | OutputPort]:
        """Get a port by name, or None if not found."""
        return self._ports.get(name)

    @property
    def names(self) -> tuple[str, ...]:
        """Return tuple of all port names."""
        return tuple(self._ports.keys())
