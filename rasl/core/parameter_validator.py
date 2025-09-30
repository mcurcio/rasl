"""
Centralized parameter validation service for RASL.

Provides consistent parameter validation and coercion across all nodes
and components in the system.
"""

import logging
from typing import Any, Dict, Mapping, Union

logger = logging.getLogger(__name__)


class ParameterValidationError(Exception):
    """Raised when parameter validation fails."""
    pass


class ParameterValidator:
    """
    Centralized parameter validation and coercion service.
    
    Provides consistent validation logic for node parameters based on
    parameter specifications.
    """
    
    def __init__(self):
        pass
    
    def validate_and_coerce(self, param_spec: Mapping[str, Mapping[str, Any]], params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and coerce parameters according to their specifications.
        
        Args:
            param_spec: Parameter specification dictionary
            params: Parameters to validate and coerce
            
        Returns:
            Dictionary of validated and coerced parameters
            
        Raises:
            ParameterValidationError: If validation fails
        """
        validated_params = {}
        
        for param_name, value in params.items():
            if param_name not in param_spec:
                raise ValueError(f"Unknown parameter: {param_name}")
            
            spec = param_spec[param_name]
            validated_value = self._validate_single_parameter(param_name, value, spec)
            validated_params[param_name] = validated_value
        
        return validated_params
    
    def _validate_single_parameter(self, param_name: str, value: Any, spec: Mapping[str, Any]) -> Any:
        """
        Validate and coerce a single parameter.
        
        Args:
            param_name: Name of the parameter
            value: Value to validate
            spec: Parameter specification
            
        Returns:
            Validated and coerced value
            
        Raises:
            ParameterValidationError: If validation fails
        """
        param_type = spec.get("type", "any")
        
        try:
            # Type coercion
            coerced_value = self._coerce_type(value, param_type)
            
            # Range validation
            if "min" in spec or "max" in spec:
                coerced_value = self._validate_range(coerced_value, spec, param_name)
            
            # Enum validation
            if "enum" in spec:
                coerced_value = self._validate_enum(coerced_value, spec, param_name)
            
            # Custom validation
            if "validator" in spec:
                coerced_value = self._apply_custom_validator(coerced_value, spec["validator"], param_name)
            
            return coerced_value
            
        except Exception as e:
            raise ParameterValidationError(f"Parameter '{param_name}' validation failed: {e}")
    
    def _coerce_type(self, value: Any, param_type: str) -> Any:
        """Coerce value to the specified type."""
        if param_type == "any":
            return value
        elif param_type == "int":
            return int(value)
        elif param_type == "float":
            return float(value)
        elif param_type == "bool":
            if isinstance(value, bool):
                return value
            elif isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            else:
                return bool(value)
        elif param_type == "str":
            return str(value)
        elif param_type == "list":
            if isinstance(value, list):
                return value
            else:
                return [value]
        else:
            # Unknown type, return as-is
            logger.warning(f"Unknown parameter type: {param_type}")
            return value
    
    def _validate_range(self, value: Union[int, float], spec: Mapping[str, Any], param_name: str) -> Union[int, float]:
        """Validate numeric range constraints."""
        min_val = spec.get("min")
        max_val = spec.get("max")
        
        if min_val is not None and value < min_val:
            raise ParameterValidationError(f"Value {value} is below minimum {min_val}")
        
        if max_val is not None and value > max_val:
            raise ParameterValidationError(f"Value {value} is above maximum {max_val}")
        
        return value
    
    def _validate_enum(self, value: Any, spec: Mapping[str, Any], param_name: str) -> Any:
        """Validate enum constraints."""
        enum_values = spec["enum"]
        
        if value not in enum_values:
            raise ParameterValidationError(f"Value {value} not in allowed values: {enum_values}")
        
        return value
    
    def _apply_custom_validator(self, value: Any, validator_func, param_name: str) -> Any:
        """Apply custom validation function."""
        try:
            return validator_func(value)
        except Exception as e:
            raise ParameterValidationError(f"Custom validation failed: {e}")
    
    def get_default_value(self, spec: Mapping[str, Any]) -> Any:
        """Get the default value for a parameter specification."""
        if "default" in spec:
            return spec["default"]
        
        param_type = spec.get("type", "any")
        
        # Type-based defaults
        if param_type == "int":
            return 0
        elif param_type == "float":
            return 0.0
        elif param_type == "bool":
            return False
        elif param_type == "str":
            return ""
        elif param_type == "list":
            return []
        else:
            return None
