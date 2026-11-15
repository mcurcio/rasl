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
