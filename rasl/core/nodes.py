"""
Base node classes for RASL.

Defines the fundamental node types:
- Node: Base class with common functionality
- Source: Generates data (no inputs)
- Transform: Processes data (inputs -> outputs)
- Sink: Consumes data (inputs, no outputs)
"""

import abc
from typing import Any, Dict, Mapping, Optional, Protocol, runtime_checkable

from .types import Frame, Liveness, NodeState, Schema
from .ports import PortsView

# Type alias for array-like data
NDArrayLike = Any  # numpy.ndarray | torch.Tensor | list | etc.


@runtime_checkable
class Node(Protocol):
    """
    Base contract for all nodes. Instances are regular Python objects.
    Implementations must be side-effect free except Sources/Sinks.
    """
    
    # Class-level type information
    KIND: str  # "source", "transform", "sink"
    TYPE: str  # Stable type name for serialization/plugin discovery
    
    def __init__(self, *, id: Optional[str] = None, **params):
        """Initialize node with optional ID and parameters."""
        ...
    
    @property
    def id(self) -> str:
        """Stable instance ID (auto-generated if not provided)."""
        ...
    
    @property
    def ports(self) -> PortsView:
        """Namespaced port references."""
        ...
    
    def port_schema(self, name: str) -> Schema:
        """Get schema for a named port."""
        ...
    
    def param_spec(self) -> Mapping[str, Mapping[str, Any]]:
        """Parameter specification for validation and UI generation."""
        ...
    
    def set_params(self, **params: Any) -> None:
        """Update parameters with validation and coercion."""
        ...
    
    def get_params(self) -> Mapping[str, Any]:
        """Get current parameter values."""
        ...


class BaseNode:
    """
    Concrete base implementation of Node protocol.
    Provides common functionality for ID generation, parameter management, etc.
    """
    
    KIND: str = "base"
    TYPE: str = "BaseNode"
    
    def __init__(self, *, id: Optional[str] = None, **params):
        self._id = id or self._generate_id()
        self._params = {}
        self._ports_view = None  # Lazy initialization
        
        # Validate and set initial parameters
        param_spec = self.param_spec()
        for key, value in params.items():
            if key not in param_spec:
                raise ValueError(f"Unknown parameter: {key}")
            # TODO: Add parameter validation based on spec
            self._params[key] = value
    
    @property
    def id(self) -> str:
        return self._id
    
    @property
    def ports(self) -> PortsView:
        if self._ports_view is None:
            self._ports_view = self._create_ports_view()
        return self._ports_view
    
    def param_spec(self) -> Mapping[str, Mapping[str, Any]]:
        """Override in subclasses to define parameters."""
        return {}
    
    def set_params(self, **params: Any) -> None:
        param_spec = self.param_spec()
        for key, value in params.items():
            if key not in param_spec:
                raise ValueError(f"Unknown parameter: {key}")
            # TODO: Add parameter validation and coercion
            self._params[key] = value
    
    def get_params(self) -> Mapping[str, Any]:
        return dict(self._params)
    
    def _generate_id(self) -> str:
        """Generate unique node ID."""
        import uuid
        return f"{self.TYPE.lower()}_{uuid.uuid4().hex[:8]}"
    
    def _create_ports_view(self) -> PortsView:
        """Create ports view for this node. Override in subclasses."""
        from .ports import SimplePortsView
        return SimplePortsView(self)
    
    def port_schema(self, name: str) -> Schema:
        """Override in subclasses to define port schemas."""
        raise NotImplementedError(f"Port schema not defined for {name}")
    
    # Node-level connections removed - use explicit port connections:
    # sine.ports.out >> console.ports.in


@runtime_checkable
class Source(Node, Protocol):
    """
    Source nodes generate data without inputs.
    Examples: SineSource, CSVSource, NetworkSource
    """
    
    LIVENESS: Liveness
    
    def open(self) -> None:
        """Acquire resources (files, network connections, etc.)."""
        ...
    
    def close(self) -> None:
        """Release resources."""
        ...
    
    def sample(self, frame: Frame) -> Mapping[str, NDArrayLike]:
        """
        Produce data for the given frame.
        Must not mutate inputs; should be non-blocking.
        Returns dict mapping port names to data arrays.
        """
        ...
    
    def duration_seconds(self) -> Optional[float]:
        """Optional: duration for FINITE media."""
        ...


class BaseSource(BaseNode):
    """Base implementation for Source nodes."""
    
    KIND = "source"
    LIVENESS = Liveness.STREAM
    
    def open(self) -> None:
        """Default implementation - override if resources needed."""
        pass
    
    def close(self) -> None:
        """Default implementation - override if resources needed."""
        pass
    
    def sample(self, frame: Frame) -> Mapping[str, NDArrayLike]:
        """Override in subclasses."""
        raise NotImplementedError("Subclasses must implement sample()")
    
    def duration_seconds(self) -> Optional[float]:
        """Override for FINITE sources."""
        return None


@runtime_checkable  
class Transform(Node, Protocol):
    """
    Transform nodes process data (inputs -> outputs).
    Examples: ScaleBias, ToRGB, ColorTemperature
    """
    
    def evaluate(self, frame: Frame, **inputs: NDArrayLike) -> Mapping[str, NDArrayLike]:
        """
        Pure computation given inputs for this frame.
        Returns dict mapping output port names to data arrays.
        """
        ...


class BaseTransform(BaseNode):
    """Base implementation for Transform nodes."""
    
    KIND = "transform"
    
    def evaluate(self, frame: Frame, **inputs: NDArrayLike) -> Mapping[str, NDArrayLike]:
        """Override in subclasses."""
        raise NotImplementedError("Subclasses must implement evaluate()")


@runtime_checkable
class Sink(Node, Protocol):
    """
    Sink nodes consume data without outputs.
    Examples: ConsoleSink, SACNSink, LIFXSink
    """
    
    def emit(self, frame: Frame, **inputs: NDArrayLike) -> None:
        """
        Called when sink should emit for this frame.
        Must be fast and non-blocking.
        """
        ...
    
    def required_rate(self) -> Optional[Mapping[str, Any]]:
        """Optional per-sink cadence requirements."""
        ...


class BaseSink(BaseNode):
    """Base implementation for Sink nodes."""
    
    KIND = "sink"
    
    def emit(self, frame: Frame, **inputs: NDArrayLike) -> None:
        """Override in subclasses."""
        raise NotImplementedError("Subclasses must implement emit()")
    
    def required_rate(self) -> Optional[Mapping[str, Any]]:
        """Override if sink has rate requirements."""
        return None


# Export the main interfaces
__all__ = [
    "Node", "Source", "Transform", "Sink",
    "BaseNode", "BaseSource", "BaseTransform", "BaseSink",
    "NDArrayLike"
]
