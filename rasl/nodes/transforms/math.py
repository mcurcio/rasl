"""
Mathematical transform nodes for basic data manipulation.
"""

from typing import Any, Dict, Mapping

from rasl.core.nodes import BaseTransform, NDArrayLike
from rasl.core.types import Frame, Schema, Component, Channel, Range


class ScaleBias(BaseTransform):
    """
    Linear transformation: output = input * scale + bias
    
    Essential building block for adjusting brightness, contrast,
    and range mapping of animation data.
    """
    
    TYPE = "ScaleBias"
    
    def __init__(self, *, scale: float = 1.0, bias: float = 0.0, **kwargs):
        super().__init__(**kwargs)
        self.scale = scale
        self.bias = bias
    
    def param_spec(self) -> Mapping[str, Mapping[str, Any]]:
        return {
            "scale": {
                "type": "float",
                "default": 1.0,
                "min": -10.0,
                "max": 10.0,
                "description": "Multiplication factor"
            },
            "bias": {
                "type": "float",
                "default": 0.0,
                "min": -10.0,
                "max": 10.0,
                "description": "Addition offset"
            }
        }
    
    def evaluate(self, frame: Frame, **inputs: NDArrayLike) -> Dict[str, NDArrayLike]:
        """Apply scale and bias transformation."""
        if "in" not in inputs:
            raise ValueError("ScaleBias requires 'in' input")
        
        input_data = inputs["in"]
        
        # Handle both single values and arrays
        if hasattr(input_data, '__iter__') and not isinstance(input_data, str):
            output_data = [x * self.scale + self.bias for x in input_data]
        else:
            output_data = input_data * self.scale + self.bias
        
        return {"out": output_data}
    
    def port_schema(self, name: str) -> Schema:
        """
        Flexible schema - accepts any number of input channels.
        
        Transform nodes should be flexible and adapt to their inputs.
        """
        if name in ("in", "out"):
            # Return empty schema for flexibility - will accept any input
            # and pass through the same structure
            return Schema(components=())
        
        raise ValueError(f"Unknown port: {name}")


class Add(BaseTransform):
    """
    Add two input streams: output = a + b
    
    Useful for combining signals, mixing animations,
    and creating composite effects.
    """
    
    TYPE = "Add"
    
    def evaluate(self, frame: Frame, **inputs: NDArrayLike) -> Dict[str, NDArrayLike]:
        """Add two input streams."""
        if "a" not in inputs or "b" not in inputs:
            raise ValueError("Add requires both 'a' and 'b' inputs")
        
        a_data = inputs["a"]
        b_data = inputs["b"]
        
        # Handle different input types
        if hasattr(a_data, '__iter__') and hasattr(b_data, '__iter__'):
            # Both are arrays - element-wise addition
            if not isinstance(a_data, str) and not isinstance(b_data, str):
                output_data = [a + b for a, b in zip(a_data, b_data)]
            else:
                raise ValueError("Cannot add string data")
        elif hasattr(a_data, '__iter__') and not isinstance(a_data, str):
            # a is array, b is scalar
            output_data = [a + b_data for a in a_data]
        elif hasattr(b_data, '__iter__') and not isinstance(b_data, str):
            # a is scalar, b is array
            output_data = [a_data + b for b in b_data]
        else:
            # Both scalars
            output_data = a_data + b_data
        
        return {"out": output_data}
    
    def port_schema(self, name: str) -> Schema:
        """Define input and output schemas."""
        if name in ("a", "b", "out"):
            return Schema(components=(
                Component(
                    name="Scalar",
                    channels=(Channel("value", "unitless", Range()),)
                ),
            ))
        
        raise ValueError(f"Unknown port: {name}")


class Multiply(BaseTransform):
    """
    Multiply two input streams: output = a * b
    
    Useful for amplitude modulation, gating effects,
    and signal conditioning.
    """
    
    TYPE = "Multiply"
    
    def evaluate(self, frame: Frame, **inputs: NDArrayLike) -> Dict[str, NDArrayLike]:
        """Multiply two input streams."""
        if "a" not in inputs or "b" not in inputs:
            raise ValueError("Multiply requires both 'a' and 'b' inputs")
        
        a_data = inputs["a"]
        b_data = inputs["b"]
        
        # Handle different input types (similar to Add)
        if hasattr(a_data, '__iter__') and hasattr(b_data, '__iter__'):
            if not isinstance(a_data, str) and not isinstance(b_data, str):
                output_data = [a * b for a, b in zip(a_data, b_data)]
            else:
                raise ValueError("Cannot multiply string data")
        elif hasattr(a_data, '__iter__') and not isinstance(a_data, str):
            output_data = [a * b_data for a in a_data]
        elif hasattr(b_data, '__iter__') and not isinstance(b_data, str):
            output_data = [a_data * b for b in b_data]
        else:
            output_data = a_data * b_data
        
        return {"out": output_data}
    
    def port_schema(self, name: str) -> Schema:
        """Define input and output schemas."""
        if name in ("a", "b", "out"):
            return Schema(components=(
                Component(
                    name="Scalar",
                    channels=(Channel("value", "unitless", Range()),)
                ),
            ))
        
        raise ValueError(f"Unknown port: {name}")


class Clamp(BaseTransform):
    """
    Clamp values to a specified range: output = clamp(input, min, max)
    
    Essential for ensuring values stay within valid bounds
    for hardware outputs and preventing overflow.
    """
    
    TYPE = "Clamp"
    
    def __init__(self, *, min_val: float = 0.0, max_val: float = 1.0, **kwargs):
        super().__init__(**kwargs)
        self.min_val = min_val
        self.max_val = max_val
    
    def param_spec(self) -> Mapping[str, Mapping[str, Any]]:
        return {
            "min_val": {
                "type": "float",
                "default": 0.0,
                "description": "Minimum output value"
            },
            "max_val": {
                "type": "float", 
                "default": 1.0,
                "description": "Maximum output value"
            }
        }
    
    def evaluate(self, frame: Frame, **inputs: NDArrayLike) -> Dict[str, NDArrayLike]:
        """Clamp input values to range."""
        if "in" not in inputs:
            raise ValueError("Clamp requires 'in' input")
        
        input_data = inputs["in"]
        
        def clamp_value(x):
            return max(self.min_val, min(self.max_val, x))
        
        if hasattr(input_data, '__iter__') and not isinstance(input_data, str):
            output_data = [clamp_value(x) for x in input_data]
        else:
            output_data = clamp_value(input_data)
        
        return {"out": output_data}
    
    def port_schema(self, name: str) -> Schema:
        """Define schemas with clamped range."""
        if name == "in":
            return Schema(components=(
                Component(
                    name="Scalar",
                    channels=(Channel("value", "unitless", Range()),)
                ),
            ))
        elif name == "out":
            return Schema(components=(
                Component(
                    name="Scalar", 
                    channels=(Channel("value", "unitless", Range(self.min_val, self.max_val)),)
                ),
            ))
        
        raise ValueError(f"Unknown port: {name}")
