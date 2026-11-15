"""Typed quantities for node configuration: ``Duration`` and ``Frequency``.

A node declares a setting with one of these as its type and reads a typed
value; the config text is parsed and checked once, when the config loads::

    class Config(TransformNodeConfig):
        smooth_period: Duration = Duration("50ms")
        fps: Frequency = Frequency(30)

    ...
    self._tau = config.smooth_period.seconds
    self._hz = config.fps.hz

Each type accepts only its own kind of unit, so a config cannot say one thing
and mean another:

- ``Duration``: a number with a time unit (``50ms``, ``2s``, ``1.5min``).
  A bare number is refused: it does not say what it counts.
- ``Frequency``: a number of hertz, bare or with ``hz`` or ``fps``
  (``30``, ``20hz``, ``30fps``).
"""

from __future__ import annotations

import math
from functools import lru_cache, total_ordering
from typing import Any, ClassVar

import pint
from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

# Create a shared unit registry
_ureg = pint.UnitRegistry()

# Define custom aliases for convenience
_ureg.define("fps = 1 * hertz")  # frames per second = hz
_ureg.define("hz = 1 * hertz")  # shorthand for hertz

_TIME = "[time]"
_FREQUENCY = "1 / [time]"


@lru_cache(maxsize=256)
def _parse(text: str) -> tuple[float, str]:
    """A written value as (magnitude in seconds or hertz, kind).

    Returns:
        ``(seconds, "time")``, ``(hertz, "frequency")`` or ``(number, "number")``
        for a bare number.

    Raises:
        ValueError: If the text is not a number with an optional time or
            frequency unit.
    """
    cleaned = text.strip().lower()
    try:
        quantity = _ureg.parse_expression(cleaned)
    except Exception as error:  # pint raises several unrelated types
        raise ValueError(f"cannot read {text!r} as a number with a unit") from error

    if isinstance(quantity, (int, float)):
        return float(quantity), "number"
    if not isinstance(quantity, pint.Quantity):
        raise ValueError(f"cannot read {text!r} as a number with a unit")
    if quantity.dimensionless:
        return float(quantity.magnitude), "number"
    if quantity.check(_TIME):
        return float(quantity.to("second").magnitude), "time"
    if quantity.check(_FREQUENCY):
        return float(quantity.to("hertz").magnitude), "frequency"
    raise ValueError(f"{text!r} is neither a time nor a frequency")


def _format(value: float) -> str:
    """A number without a trailing ``.0``."""
    return f"{value:g}"


@total_ordering
class _Quantity:
    """What ``Duration`` and ``Frequency`` share: one float, compared and hashed
    by value, never changed, and read by pydantic from config text."""

    __slots__ = ("_value",)
    _value: float

    _json_schema: ClassVar[dict[str, Any]]

    def __eq__(self, other: object) -> bool:
        return type(other) is type(self) and other._value == self._value  # type: ignore[attr-defined]

    def __lt__(self, other: object) -> bool:
        if type(other) is not type(self):
            return NotImplemented
        return self._value < other._value  # type: ignore[attr-defined]

    def __hash__(self) -> int:
        return hash((type(self), self._value))

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(f"{type(self).__name__} cannot be changed")

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str(self)!r})"

    @classmethod
    def _validate(cls, value: Any) -> Any:
        return value if isinstance(value, cls) else cls(value)

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.plain_serializer_function_ser_schema(str, when_used="json"),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return dict(cls._json_schema)


class Duration(_Quantity):
    """A length of time.

    Written as a number with a time unit: ``50ms``, ``2s``, ``1.5min``. Zero
    is allowed (many settings read it as "off"); a negative time is not.

    Examples:
        >>> Duration("50ms").seconds
        0.05
        >>> Duration(seconds=2).seconds
        2.0
        >>> str(Duration("1.5s"))
        '1.5s'
    """

    __slots__ = ()
    _json_schema = {
        "type": "string",
        "format": "rasl-duration",
        "description": "A number with a time unit",
        "examples": ["50ms", "2s", "1.5min"],
    }

    def __init__(self, text: str | None = None, *, seconds: float | None = None) -> None:
        """Parse a written duration, or take a number of seconds by name.

        Args:
            text: The duration as a config writes it, such as ``"50ms"``.
            seconds: Instead of ``text``: the duration in seconds.

        Raises:
            ValueError: If the text is a bare number, a frequency, negative,
                or not a number with a time unit.
        """
        if (text is None) == (seconds is None):
            raise TypeError("Duration takes either a written value or seconds=")
        if seconds is None:
            if isinstance(text, bool) or not isinstance(text, (str, int, float)):
                raise ValueError(f"a duration is written as a number with a time unit, such as 50ms (got {text!r})")
            if isinstance(text, (int, float)):
                raise ValueError(
                    f"a duration needs a unit, such as {_format(text)}ms or {_format(text)}s (got {_format(text)})"
                )
            magnitude, kind = _parse(text)
            if kind == "number":
                shown = _format(magnitude)
                raise ValueError(f"a duration needs a unit, such as {shown}ms or {shown}s (got {text!r})")
            if kind == "frequency":
                raise ValueError(f"a duration takes a time, such as 50ms or 2s, not a frequency (got {text!r})")
            seconds = magnitude
        seconds = float(seconds)
        if not math.isfinite(seconds) or seconds < 0.0:
            raise ValueError(f"a duration cannot be negative (got {text if text is not None else seconds!r})")
        object.__setattr__(self, "_value", seconds)

    @property
    def seconds(self) -> float:
        """The duration in seconds."""
        return self._value

    @property
    def milliseconds(self) -> float:
        """The duration in milliseconds."""
        return self._value * 1000.0

    def __bool__(self) -> bool:
        """False for a zero duration."""
        return self._value > 0.0

    def __str__(self) -> str:
        if self._value == 0.0 or self._value >= 1.0:
            return f"{_format(self._value)}s"
        return f"{_format(self._value * 1000.0)}ms"


class Frequency(_Quantity):
    """How often something happens, in hertz.

    Written as a number of hertz, bare or with ``hz`` or ``fps``: ``30``,
    ``20hz``, ``30fps``. It must be positive.

    Examples:
        >>> Frequency(30).hz
        30.0
        >>> Frequency("20hz").period.seconds
        0.05
        >>> str(Frequency("2.5fps"))
        '2.5hz'
    """

    __slots__ = ()
    _json_schema = {
        "anyOf": [{"type": "number", "exclusiveMinimum": 0}, {"type": "string", "format": "rasl-frequency"}],
        "description": "A number of hertz, bare or with hz or fps",
        "examples": [30, "20hz", "30fps"],
    }

    def __init__(self, value: str | float | None = None, *, hz: float | None = None) -> None:
        """Parse a written frequency, or take a number of hertz.

        Args:
            value: The frequency as a config writes it: a number of hertz, or
                text such as ``"20hz"``.
            hz: Instead of ``value``: the frequency in hertz.

        Raises:
            ValueError: If the value is a time, not positive, or not a number
                of hertz.
        """
        if (value is None) == (hz is None):
            raise TypeError("Frequency takes either a written value or hz=")
        if hz is None:
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise ValueError(f"a frequency is a number of hertz, such as 30, 30hz or 30fps (got {value!r})")
            if isinstance(value, (int, float)):
                hz = float(value)
            else:
                magnitude, kind = _parse(value)
                if kind == "time":
                    raise ValueError(
                        f"a frequency takes a number of hertz, such as 30, 30hz or 30fps, not a time (got {value!r})"
                    )
                hz = magnitude
        hz = float(hz)
        if not math.isfinite(hz) or hz <= 0.0:
            raise ValueError(f"a frequency must be positive (got {value if value is not None else hz!r})")
        object.__setattr__(self, "_value", hz)

    @property
    def hz(self) -> float:
        """The frequency in hertz."""
        return self._value

    @property
    def period(self) -> Duration:
        """The time one cycle takes."""
        return Duration(seconds=1.0 / self._value)

    def __str__(self) -> str:
        return f"{_format(self._value)}hz"
