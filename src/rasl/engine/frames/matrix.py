"""Matrix payload types for numeric signal data.

This module defines MatrixPayload (the base for all numeric signals)
and BoolPayload for boolean data.
"""

from __future__ import annotations

from typing import Any, ClassVar, Type

import numpy as np
from numpy.typing import NDArray

from .base import FramePayload, PayloadDescriptor
from ..registry import payload


@payload("matrix")
@payload("array")  # Alias for backwards compatibility
class MatrixPayload(FramePayload):
    """Base for all numeric signal types.
    
    MatrixPayload represents a 2D numeric matrix with shape (count, channels).
    This is the universal currency for signal data in RASL - all numeric
    frame types derive from this.
    
    Shape convention:
    - count: First dimension (number of elements, e.g., number of pixels)
    - channels: Second dimension (dimensions per element, e.g., 3 for RGB)
    - size = count * channels
    
    For 1D arrays, the data is normalized to shape (count, 1).
    
    Attributes:
        data: The underlying numpy array (float32, shape (count, channels))
    """

    __slots__ = ("_data",)
    domain: ClassVar[str] = "matrix"

    def __init__(self, data: NDArray[np.float32]) -> None:
        arr = np.asarray(data, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        if arr.ndim != 2:
            raise ValueError(
                f"MatrixPayload data must be 1D or 2D, got shape {arr.shape!r}"
            )
        self._data = arr

    @property
    def data(self) -> NDArray[np.float32]:
        return self._data

    @property
    def channels(self) -> int:
        return self._data.shape[1]

    @property
    def dimensions(self) -> int:
        return self.channels

    @property
    def count(self) -> int:
        return self._data.shape[0]

    @property
    def size(self) -> int:
        return int(self._data.size)

    def __array__(self, dtype: Any | None = None) -> NDArray[np.float32]:
        if dtype is not None:
            return np.asarray(self._data, dtype=dtype)
        return self._data

    def __getitem__(self, item: Any) -> Any:
        return self._data[item]

    def flatten(self) -> NDArray[np.float32]:
        return np.asarray(self._data, dtype=np.float32).ravel()

    def repeat(self, n: int) -> "MatrixPayload":
        if n <= 1:
            return self
        repeated = np.tile(self._data, (n, 1))
        return MatrixPayload(repeated)

    def __len__(self) -> int:  # pragma: no cover - trivial delegation
        return self.count

    def describe(self) -> PayloadDescriptor:
        return PayloadDescriptor(
            type_name="MatrixPayload",
            domain=self.domain,
            attrs={
                "shape": self._data.shape,
                "channels": self.channels,
                "dimensions": self.dimensions,
                "count": self.count,
                "size": self.size,
                "dtype": str(self._data.dtype),
            },
        )

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """MatrixPayload accepts any MatrixPayload subclass."""
        return issubclass(other, MatrixPayload)

    @classmethod
    def ensure_buffer(
        cls,
        buffer: object | None,
        *,
        count: int,
        components: int,
    ) -> "NDArray[np.float32]":
        return super().ensure_buffer(
            buffer,
            count=count,
            components=components,
        )

    def __repr__(self) -> str:
        """Return a compact summary: Frame<len=x data=[[...], ...]>."""

        data = self._data

        def _fmt(v: float) -> str:
            iv = int(v)
            if float(iv) == float(v):
                return str(iv)
            return (f"{float(v):.3f}".rstrip("0").rstrip("."))

        rows = [row.tolist() for row in data]

        total = len(rows)
        max_rows = 20
        shown_rows = rows[:max_rows]

        row_strs: list[str] = []
        for row in shown_rows:
            row_str = ",".join(_fmt(float(v)) for v in row)
            row_strs.append(f"[{row_str}]")

        data_str = "[" + ",".join(row_strs)
        if total > max_rows:
            data_str += ",..."
        data_str += "]"

        return f"Frame<len={total} data={data_str}>"


@payload("bool")
@payload("boolean")
class BoolPayload(MatrixPayload):
    __slots__ = ()
    domain: ClassVar[str] = "bool"

    def __init__(self, data: NDArray[np.float32]) -> None:
        arr = np.asarray(data)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        if arr.ndim != 2:
            raise ValueError(
                f"BoolPayload data must be 1D or 2D, got shape {arr.shape!r}"
            )
        normalized = (arr != 0).astype(np.float32)
        super().__init__(normalized)
