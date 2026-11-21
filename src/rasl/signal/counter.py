"""RollingCounter: a count that wraps, carried as a payload.

A counter is not a matrix: it has no rows, no columns and no backing array, so it
cannot be sliced, repeated or merged with other sources into one port (the graph
refuses those at load).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Type

from rasl.signal.payload import FramePayload, PayloadDescriptor
from rasl.signal.registry import payload


@payload("counter")
@dataclass(frozen=True, slots=True)
class RollingCounter(FramePayload):
    """A count that wraps at ``modulus``; compare two readings with ``advanced_since``.

    Immutable, so it is safe to hand on by reference. Two readings ``modulus`` or more
    steps apart alias: with the default modulus of 65536, a counter advanced once per
    sACN packet at 44 Hz aliases after more than 24 minutes between reads.

    Attributes:
        value: The count, in ``[0, modulus)``.
        modulus: The count wraps to 0 on reaching this; at least 2. Default 65536.

    Raises:
        ValueError: On construction, if ``modulus`` is below 2 or ``value`` is outside
            ``[0, modulus)``.
    """

    domain: ClassVar[str] = "counter"
    DEFAULT_MODULUS: ClassVar[int] = 1 << 16

    value: int = 0
    modulus: int = DEFAULT_MODULUS

    def __post_init__(self) -> None:
        """Check the modulus and the value's range.

        Raises:
            ValueError: If ``modulus`` is below 2 or ``value`` is outside ``[0, modulus)``.
        """
        if self.modulus < 2:
            raise ValueError(f"RollingCounter modulus must be at least 2, got {self.modulus}")
        if not 0 <= self.value < self.modulus:
            raise ValueError(
                f"RollingCounter value must be in [0, {self.modulus}), got {self.value}"
            )

    def advanced(self, by: int = 1) -> RollingCounter:
        """A new counter ``by`` steps on, wrapped into ``[0, modulus)``; this one is unchanged.

        ``by`` may be negative or larger than the modulus.
        """
        return RollingCounter((self.value + by) % self.modulus, self.modulus)

    def advanced_since(self, previous: RollingCounter) -> int:
        """Steps from ``previous`` to this reading, in ``[0, modulus)``, counting across the wrap.

        Raises:
            ValueError: If ``previous`` has another modulus.
        """
        if previous.modulus != self.modulus:
            raise ValueError(
                f"Cannot compare counters of modulus {self.modulus} and {previous.modulus}"
            )
        return (self.value - previous.value) % self.modulus

    @classmethod
    def coerces_from(cls, other: Type[FramePayload]) -> bool:
        """Always False: no other payload, not even a ``FramePayload``, is made a counter."""
        return False

    def describe(self) -> PayloadDescriptor:
        """Describe the counter: class name, domain ``counter``, and its value and modulus."""
        return PayloadDescriptor(
            type_name=type(self).__name__,
            domain=self.domain,
            attrs={"value": self.value, "modulus": self.modulus},
        )
