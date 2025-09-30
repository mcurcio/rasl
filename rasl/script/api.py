"""
User-facing API for RASL scripts.

Provides functions that users can call in their scripts to expose
parameters and interact with the RASL runtime.
"""

from typing import Any, Dict, Optional, Union
import threading

# Global state for script execution context
_script_context = threading.local()


class ParameterExport:
    """Represents a parameter exposed for UI control."""
    
    def __init__(
        self,
        node_path: str,
        param_name: str,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
        step: Optional[float] = None,
        enum_values: Optional[list] = None,
        description: Optional[str] = None
    ):
        self.node_path = node_path
        self.param_name = param_name
        self.min_val = min_val
        self.max_val = max_val
        self.step = step
        self.enum_values = enum_values
        self.description = description
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "node_path": self.node_path,
            "param_name": self.param_name,
            "min": self.min_val,
            "max": self.max_val,
            "step": self.step,
            "enum": self.enum_values,
            "description": self.description
        }


def expose_parameter(
    parameter_path: str,
    *,
    min: Optional[float] = None,
    max: Optional[float] = None,
    step: Optional[float] = None,
    enum: Optional[list] = None,
    description: Optional[str] = None
) -> None:
    """
    Expose a node parameter for UI control.
    
    Args:
        parameter_path: Path to parameter in format "node_id.param_name"
        min: Minimum value for numeric parameters
        max: Maximum value for numeric parameters  
        step: Step size for UI controls
        enum: List of allowed values for enum parameters
        description: Human-readable description
    
    Example:
        expose_parameter("sine.freq", min=0.1, max=10.0, step=0.1)
        expose_parameter("effect.mode", enum=["fade", "strobe", "chase"])
    """
    if "." not in parameter_path:
        raise ValueError(f"Parameter path must be in format 'node_id.param_name', got: {parameter_path}")
    
    node_path, param_name = parameter_path.rsplit(".", 1)
    
    # Store in thread-local context
    if not hasattr(_script_context, 'exposed_parameters'):
        _script_context.exposed_parameters = []
    
    param_export = ParameterExport(
        node_path=node_path,
        param_name=param_name,
        min_val=min,
        max_val=max,
        step=step,
        enum_values=enum,
        description=description
    )
    
    _script_context.exposed_parameters.append(param_export)


def get_exposed_parameters() -> list[ParameterExport]:
    """Get all parameters exposed in the current script context."""
    if not hasattr(_script_context, 'exposed_parameters'):
        return []
    return list(_script_context.exposed_parameters)


def clear_exposed_parameters() -> None:
    """Clear all exposed parameters (used when reloading scripts)."""
    if hasattr(_script_context, 'exposed_parameters'):
        _script_context.exposed_parameters.clear()


def get_engine():
    """
    Get reference to the current RASL engine.
    
    This allows scripts to interact with the engine directly,
    though this should be used sparingly.
    
    Returns:
        Engine instance or None if not available
    """
    return getattr(_script_context, 'engine', None)


def _set_engine(engine) -> None:
    """Internal: Set the engine reference for script context."""
    _script_context.engine = engine


def _get_script_context() -> Dict[str, Any]:
    """Internal: Get all script context data."""
    return {
        'exposed_parameters': get_exposed_parameters(),
        'engine': get_engine()
    }


def _clear_script_context() -> None:
    """Internal: Clear all script context data."""
    if hasattr(_script_context, 'exposed_parameters'):
        _script_context.exposed_parameters.clear()
    if hasattr(_script_context, 'engine'):
        _script_context.engine = None


# Convenience functions for common parameter patterns
def expose_frequency(node_id: str, min_hz: float = 0.1, max_hz: float = 10.0) -> None:
    """Expose a frequency parameter with sensible defaults."""
    expose_parameter(f"{node_id}.freq", min=min_hz, max=max_hz, step=0.1, 
                    description="Frequency in Hz")


def expose_amplitude(node_id: str, max_amp: float = 2.0) -> None:
    """Expose an amplitude parameter with sensible defaults."""
    expose_parameter(f"{node_id}.amplitude", min=0.0, max=max_amp, step=0.01,
                    description="Signal amplitude")


def expose_color_temp(node_id: str) -> None:
    """Expose color temperature parameters."""
    expose_parameter(f"{node_id}.min_temp", min=1000, max=4000, step=100,
                    description="Minimum color temperature (K)")
    expose_parameter(f"{node_id}.max_temp", min=4000, max=8000, step=100, 
                    description="Maximum color temperature (K)")


def expose_scale_bias(node_id: str) -> None:
    """Expose scale and bias parameters."""
    expose_parameter(f"{node_id}.scale", min=0.0, max=2.0, step=0.01,
                    description="Scaling factor")
    expose_parameter(f"{node_id}.bias", min=-1.0, max=1.0, step=0.01,
                    description="Offset bias")
