"""Base payload types for the RASL frame system.

This module defines the abstract base class for all payload types
and the PayloadDescriptor for introspection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Type

import numpy as np
from numpy.typing import NDArray


class PayloadCoercionError(ValueError):
    """A payload that cannot be retyped as the more specific type a port takes.

    Attributes:
        supplied: For a width mismatch, the columns the payload has; else None.
        takes: For a width mismatch, the components the type takes; else None.
    """

    def __init__(self, message: str, *, supplied: int | None = None, takes: int | None = None) -> None:
        super().__init__(message)
        self.supplied = supplied
        self.takes = takes


@dataclass(frozen=True)
class PayloadDescriptor:
    """Introspection metadata for any payload."""

    type_name: str
    domain: str
    attrs: dict[str, Any]


class FramePayload:
    """Abstract base for all payload types."""

    __slots__ = ()
    components: ClassVar[int | None] = None

    domain: ClassVar[str] = "payload"

    def describe(self) -> PayloadDescriptor:
        """Describe the payload: its class name and domain, with no attributes."""
        return PayloadDescriptor(
            type_name=type(self).__name__,
            domain=self.domain,
            attrs={},
        )

    @classmethod
    def ensure_buffer(
        cls,
        buffer: object | None,
        *,
        count: int,
        components: int,
    ) -> "NDArray[np.float32]":
        """Ensure a writable backing buffer exists and is large enough.

        This is the single place where real NumPy storage allocation should
        happen for a given payload family.
        """
        if count < 0:
            raise ValueError(f"count must be non-negative, got {count}")
        if components <= 0:
            raise ValueError(f"components must be > 0, got {components}")

        arr = None if buffer is None else np.asarray(buffer)
        if arr is None or arr.ndim != 2 or arr.shape[1] != components or arr.shape[0] < count:
            rows = count if arr is None or arr.ndim != 2 else max(count, arr.shape[0])
            return np.zeros((rows, components), dtype=np.float32)
        return arr

    @classmethod
    def coerces_from(cls, other: Type[FramePayload]) -> bool:
        """Whether a port of this type takes ``other`` by retyping it, with no converter node.

        Owner, 2026-11-16: "all types have an inheritance chain and should be allowed to
        coerce a more general type to a more specific type implicitly". So ``cls`` takes
        any strict ancestor of itself (a ``MatrixPayload`` into a ``BoolPayload`` or an
        ``RgbColorPayload`` port). A type that cannot be made from a general payload
        says so by overriding this.
        """
        return other is not cls and issubclass(cls, other)

    @classmethod
    def coerce(cls, payload: FramePayload) -> FramePayload:
        """``payload`` as this type: unchanged when it already is one, else retyped.

        Raises:
            PayloadCoercionError: If ``payload`` cannot be this type (a type outside the
                chain, a matrix of the wrong width, a color of another model).
        """
        if isinstance(payload, cls):
            return payload
        raise PayloadCoercionError(f"{type(payload).__name__} cannot be made a {cls.__name__}")

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """Check if `other` type can be accepted by ports expecting `cls`.

        Default: standard subclass check.
        Override in subclasses to define domain-specific compatibility.
        """
        return issubclass(other, cls)
