"""Base payload types for the RASL frame system.

This module defines the abstract base class for all payload types
and the PayloadDescriptor for introspection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Type

import numpy as np
from numpy.typing import NDArray


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
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """Check if `other` type can be accepted by ports expecting `cls`.

        Default: standard subclass check.
        Override in subclasses to define domain-specific compatibility.
        """
        return issubclass(other, cls)
