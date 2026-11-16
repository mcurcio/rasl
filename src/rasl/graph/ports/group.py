"""A node's ports, by name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Optional

from rasl.graph.ports.port import InputPort, OutputPort
from rasl.graph.ports.spec import InputPortSpec, OutputPortSpec

if TYPE_CHECKING:
    pass


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


class PortGroup:
    """Named collection of input or output ports.

    PortGroup creates InputPort or OutputPort objects directly as attributes,
    providing fast attribute access without dynamic lookup. Use the factory
    methods `inputs()` and `outputs()` to create port groups.

    Example:
        >>> from rasl.color import ColorPayload
        >>> from rasl.signal import MatrixPayload
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
        object.__setattr__(self, "_default", None)
        
        # Create port objects directly as attributes
        for name, spec in ports.items():
            if _is_input:
                port = InputPort(name=name, spec=spec)
            else:
                port = OutputPort(name=name, spec=spec)
            object.__setattr__(self, name, port)

    def clone(self) -> "PortGroup":
        """A new group with the same specs and its own port objects.

        A node class declares its ports once, as class attributes; each node
        made from the class gets a clone, so no two nodes share a port's
        frame or buffers.
        """
        group = PortGroup(
            _is_input=self._is_input,
            **{name: getattr(self, name).spec for name in self._port_names},
        )
        object.__setattr__(group, "_default", self._default)
        return group

    def with_default(self, name: str) -> "PortGroup":
        """A copy of this group whose default port is ``name``.

        The default port is the one a config's ``connect`` uses when it names no port
        (``connect source;``). Without this, a group has a default only when it has a
        single port.

        Raises:
            ValueError: If the group has no port called ``name``.
        """
        if name not in self._port_names:
            raise ValueError(f"No port '{name}' to make the default; ports: {self._port_names}")
        group = self.clone()
        object.__setattr__(group, "_default", name)
        return group

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

        The port named by ``with_default``, or else the sole port of a one-port group.

        Returns:
            Tuple of (port_name, port_object).

        Raises:
            ValueError: If no default was set and the group has zero or several ports.
        """
        if self._default is not None:
            return (self._default, getattr(self, self._default))
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
