"""Unit parsing utilities for RASL configuration.

This module provides functions to parse values with optional unit suffixes
using the pint library. Supports common time and frequency units.

Examples:
    >>> parse_interval("30hz")  # Returns 0.0333... (seconds)
    >>> parse_interval("20ms")  # Returns 0.02 (seconds)
    >>> parse_interval("30")    # Returns 0.0333... (assumes hz)
    >>> parse_interval(0.05)    # Returns 0.05 (passthrough)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Union

import pint

# Create a shared unit registry
_ureg = pint.UnitRegistry()

# Define custom aliases for convenience
_ureg.define("fps = 1 * hertz")  # frames per second = hz
_ureg.define("hz = 1 * hertz")  # shorthand for hertz


@lru_cache(maxsize=128)
def _parse_cached(value: str, default_unit: str) -> pint.Quantity:
    """Parse a string value with optional unit suffix (cached).

    Args:
        value: String value, optionally with unit suffix.
        default_unit: Unit to assume if none specified.

    Returns:
        Pint Quantity with appropriate units.
    """
    value = value.strip().lower()

    # Try to parse with pint
    try:
        quantity = _ureg.parse_expression(value)
        # If it's just a number (no units), apply default
        if not hasattr(quantity, 'dimensionality') or quantity.dimensionless:
            numeric = float(quantity.magnitude if hasattr(quantity, 'magnitude') else quantity)
            quantity = numeric * _ureg(default_unit)
    except pint.UndefinedUnitError:
        # No unit found, assume default
        try:
            numeric = float(value)
            quantity = numeric * _ureg(default_unit)
        except ValueError:
            raise ValueError(f"Cannot parse value: {value!r}")

    return quantity


def parse_interval(value: Union[str, int, float], default_unit: str = "hz") -> float:
    """Parse a time interval or frequency value to seconds.

    Accepts:
        - Frequency: "30hz", "30fps", "30" (assumes hz by default)
        - Time: "20ms", "50ms", "0.05s"
        - Numeric: 30 (assumes hz), 0.05 (if < 1, assumes seconds)

    Args:
        value: String with optional unit, or numeric value.
        default_unit: Unit to assume for bare numbers (default: "hz").

    Returns:
        Interval in seconds.

    Examples:
        >>> parse_interval("30hz")
        0.03333333333333333
        >>> parse_interval("20ms")
        0.02
        >>> parse_interval("30")
        0.03333333333333333
        >>> parse_interval(30)
        0.03333333333333333
        >>> parse_interval(0.05)
        0.05
    """
    if isinstance(value, (int, float)):
        # Numeric value: assume hz if >= 1, seconds if < 1
        if value >= 1:
            return 1.0 / value
        else:
            return float(value)

    quantity = _parse_cached(value, default_unit)

    # Convert to seconds
    if quantity.dimensionality == {"[time]": 1}:
        # Already a time unit (ms, s, etc.)
        return quantity.to("seconds").magnitude
    elif quantity.dimensionality == {"[time]": -1}:
        # Frequency unit (hz, fps)
        return 1.0 / quantity.to("hertz").magnitude
    else:
        raise ValueError(
            f"Cannot convert {value!r} to time interval. "
            "Expected frequency (hz, fps) or time (ms, s)."
        )


def parse_frequency(value: Union[str, int, float], default_unit: str = "hz") -> float:
    """Parse a frequency value to hertz.

    Accepts:
        - Frequency: "30hz", "30fps", "30" (assumes hz by default)
        - Time: "20ms" (converts to 50hz)
        - Numeric: 30 (assumes hz)

    Args:
        value: String with optional unit, or numeric value.
        default_unit: Unit to assume for bare numbers (default: "hz").

    Returns:
        Frequency in hertz.

    Examples:
        >>> parse_frequency("30hz")
        30.0
        >>> parse_frequency("20ms")
        50.0
        >>> parse_frequency(30)
        30.0
    """
    if isinstance(value, (int, float)):
        return float(value)

    quantity = _parse_cached(value, default_unit)

    # Convert to hertz
    if quantity.dimensionality == {"[time]": -1}:
        # Already a frequency unit (hz, fps)
        return quantity.to("hertz").magnitude
    elif quantity.dimensionality == {"[time]": 1}:
        # Time unit - convert to frequency
        seconds = quantity.to("seconds").magnitude
        return 1.0 / seconds
    else:
        raise ValueError(
            f"Cannot convert {value!r} to frequency. "
            "Expected frequency (hz, fps) or time (ms, s)."
        )
