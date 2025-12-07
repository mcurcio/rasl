"""Frame data model for the RASL processing DAG.

This module defines the immutable Frame dataclass that represents
a normalized payload flowing through the node graph. Frames carry
channel data as float32 arrays (0.0-1.0 normalized) along with
routing metadata.

Payload types are registered via the @payload decorator, enabling
a plugin architecture where the port system references types by name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, MutableMapping, Type

import numpy as np
from numpy.typing import NDArray

from .registry import payload


@dataclass(frozen=True)
class PayloadDescriptor:
    """Introspection metadata for any payload."""

    type_name: str
    domain: str
    attrs: dict[str, Any]


class FramePayload:
    """Abstract base for all payload types."""

    __slots__ = ()

    domain: ClassVar[str] = "payload"

    def describe(self) -> PayloadDescriptor:
        return PayloadDescriptor(
            type_name=type(self).__name__,
            domain=self.domain,
            attrs={},
        )

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """Check if `other` type can be accepted by ports expecting `cls`.

        Default: standard subclass check.
        Override in subclasses to define domain-specific compatibility.
        """
        return issubclass(other, cls)


@payload("array")
class ArrayPayload(FramePayload):
    """Wraps a numpy float32 array."""

    __slots__ = ("_data",)
    domain: ClassVar[str] = "array"

    def __init__(self, data: NDArray[np.float32]) -> None:
        self._data = data

    @property
    def data(self) -> NDArray[np.float32]:
        return self._data

    def __array__(self, dtype: Any | None = None) -> NDArray[np.float32]:
        if dtype is not None:
            return np.asarray(self._data, dtype=dtype)
        return self._data

    def __getitem__(self, item: Any) -> Any:
        return self._data[item]

    def __len__(self) -> int:  # pragma: no cover - trivial delegation
        return len(self._data)

    def describe(self) -> PayloadDescriptor:
        return PayloadDescriptor(
            type_name="ArrayPayload",
            domain=self.domain,
            attrs={"shape": self._data.shape, "dtype": str(self._data.dtype)},
        )

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """ArrayPayload accepts any ArrayPayload subclass (including ColorPayload)."""
        return issubclass(other, ArrayPayload)


@payload("color")
class ColorPayload(ArrayPayload):
    """Base for color-domain payloads.
    
    ColorPayload wraps color data with a model tag indicating the color space.
    Use `to_model()` to convert between color spaces.
    
    Supported models: srgb, rgb, hsl, oklch, oklab, okhsl, okhsv
    """

    __slots__ = ("_model", "_encoding")
    domain: ClassVar[str] = "color"

    def __init__(
        self,
        data: NDArray[np.float32],
        model: str,
        encoding: str = "srgb",
    ) -> None:
        super().__init__(data)
        object.__setattr__(self, "_model", model.lower())
        object.__setattr__(self, "_encoding", encoding)

    @property
    def model(self) -> str:
        return self._model

    @property
    def encoding(self) -> str:
        return self._encoding

    def to_model(self, target: str) -> "ColorPayload":
        """Convert to a different color model.
        
        Returns self if already in the target model.
        
        Args:
            target: Target color model name (srgb, oklch, okhsl, etc.)
            
        Returns:
            ColorPayload in the target color space.
        """
        target = target.lower()
        if target == "rgb":
            target = "srgb"
            
        if self._model == target:
            return self
            
        # Import here to avoid circular dependency
        from rasl.engine.color.convert import convert
        
        converted = convert(self._data, self._model, target)
        return ColorPayload(converted, model=target, encoding=self._encoding)

    def describe(self) -> PayloadDescriptor:
        return PayloadDescriptor(
            type_name=type(self).__name__,
            domain=self.domain,
            attrs={
                "model": self._model,
                "encoding": self._encoding,
                "shape": self._data.shape,
            },
        )

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """ColorPayload accepts any ArrayPayload (will be tagged/converted)."""
        return issubclass(other, ArrayPayload)


@payload("rgb")
class RgbColorPayload(ColorPayload):
    """RGB color payload."""

    __slots__ = ()

    def __init__(self, data: NDArray[np.float32], encoding: str = "srgb") -> None:
        super().__init__(data, model="rgb", encoding=encoding)

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """RgbColorPayload accepts any ArrayPayload (raw or color)."""
        return issubclass(other, ArrayPayload)


@payload("hsl")
class HslColorPayload(ColorPayload):
    """HSL color payload."""

    __slots__ = ()

    def __init__(self, data: NDArray[np.float32], encoding: str = "srgb") -> None:
        super().__init__(data, model="hsl", encoding=encoding)

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """HslColorPayload accepts any ArrayPayload (raw or color)."""
        return issubclass(other, ArrayPayload)


@payload("oklch")
class OklchColorPayload(ColorPayload):
    """OKLCH color payload - perceptually uniform cylindrical space.

    OKLCH is the recommended internal color model for animation and mixing
    due to its perceptual uniformity. Components are:
    - L: Lightness [0, 1]
    - C: Chroma (saturation) [0, ~0.4 for sRGB gamut]
    - H: Hue [0, 1] (normalized, not degrees)
    """

    __slots__ = ()

    def __init__(self, data: NDArray[np.float32], encoding: str = "srgb") -> None:
        super().__init__(data, model="oklch", encoding=encoding)

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """OklchColorPayload accepts any ArrayPayload (raw or color)."""
        return issubclass(other, ArrayPayload)


@payload("oklab")
class OklabColorPayload(ColorPayload):
    """Oklab color payload - perceptually uniform cartesian space.

    Oklab is the cartesian form of OKLCH. Components are:
    - L: Lightness [0, 1]
    - a: Green-red axis [-0.4, 0.4]
    - b: Blue-yellow axis [-0.4, 0.4]
    """

    __slots__ = ()

    def __init__(self, data: NDArray[np.float32], encoding: str = "srgb") -> None:
        super().__init__(data, model="oklab", encoding=encoding)

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """OklabColorPayload accepts any ArrayPayload (raw or color)."""
        return issubclass(other, ArrayPayload)


@payload("okhsl")
class OkhslColorPayload(ColorPayload):
    """OkHSL color payload - perceptually uniform HSL-like space.

    OkHSL is based on Oklab and provides uniform hue perception.
    Better than OKLCH for hue-based animations. Components are:
    - H: Hue [0, 1] (normalized, not degrees)
    - S: Saturation [0, 1]
    - L: Lightness [0, 1]
    """

    __slots__ = ()

    def __init__(self, data: NDArray[np.float32], encoding: str = "srgb") -> None:
        super().__init__(data, model="okhsl", encoding=encoding)

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """OkhslColorPayload accepts any ArrayPayload (raw or color)."""
        return issubclass(other, ArrayPayload)


@payload("okhsv")
class OkhsvColorPayload(ColorPayload):
    """OkHSV color payload - perceptually uniform HSV-like space.

    OkHSV is based on Oklab and provides uniform hue perception.
    Better than OKLCH for hue-based animations. Components are:
    - H: Hue [0, 1] (normalized, not degrees)
    - S: Saturation [0, 1]
    - V: Value (brightness) [0, 1]
    """

    __slots__ = ()

    def __init__(self, data: NDArray[np.float32], encoding: str = "srgb") -> None:
        super().__init__(data, model="okhsv", encoding=encoding)

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """OkhsvColorPayload accepts any ArrayPayload (raw or color)."""
        return issubclass(other, ArrayPayload)


Metadata = Mapping[str, Any]
"""Type alias for frame metadata dictionaries."""


@dataclass(frozen=True, slots=True)
class Frame:
    """Immutable payload flowing through the processing DAG.

    A Frame represents a single unit of data traveling between nodes.
    It contains normalized channel data (float32 values from 0.0 to 1.0),
    a topic for routing, a monotonic timestamp, and arbitrary metadata.

    Frames are immutable (frozen dataclass) to ensure thread-safety
    and prevent unintended side effects during concurrent processing.

    Attributes:
        topic: Routing key identifying the data source or type.
            Convention: "sacn.universe.{n}" for sACN universe data.
        timestamp: Monotonic time (seconds) when the frame was created.
            Use time.monotonic() for consistent timing.
        payload: Normalized channel data as a float32 numpy array.
            Values are in range [0.0, 1.0]. Source adapters convert
            from raw byte values (0-255); sink adapters reverse this.
        metadata: Arbitrary key-value pairs for frame context.
            Common keys: sourceUniverse, priority, sequence, colorSpace.

    Example:
        >>> import numpy as np
        >>> import time
        >>> frame = Frame(
        ...     topic="sacn.universe.1",
        ...     timestamp=time.monotonic(),
        ...     payload=np.zeros(512, dtype=np.float32),
        ...     metadata={"sourceUniverse": 1, "colorSpace": "rgb"}
        ... )
    """

    topic: str
    """Routing key identifying the data source or type."""

    timestamp: float
    """Monotonic timestamp (seconds) when the frame was created."""

    payload: FramePayload
    """Normalized channel data as float32 array with values in [0.0, 1.0]."""

    metadata: Metadata = field(default_factory=dict)
    """Arbitrary key-value pairs providing frame context."""

    def with_payload(self, payload: FramePayload) -> Frame:
        """Create a new Frame with a different payload.

        Returns a copy of this frame with the payload replaced.
        The original frame is unchanged.

        Args:
            payload: The new payload for the frame.

        Returns:
            A new Frame instance with the new payload.
        """
        return Frame(
            topic=self.topic,
            timestamp=self.timestamp,
            payload=payload,
            metadata=self.metadata,
        )

    def with_metadata(self, **updates: Any) -> Frame:
        """Create a new Frame with updated metadata.

        Returns a copy of this frame with the specified metadata keys
        added or overwritten. The original frame is unchanged.

        Args:
            **updates: Key-value pairs to add or update in metadata.

        Returns:
            A new Frame instance with merged metadata.

        Example:
            >>> new_frame = frame.with_metadata(processed=True, nodeId="patch1")
        """
        existing: MutableMapping[str, Any] = dict(self.metadata)
        existing.update(updates)
        return Frame(
            topic=self.topic,
            timestamp=self.timestamp,
            payload=self.payload,
            metadata=existing,
        )
