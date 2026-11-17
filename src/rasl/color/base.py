"""ColorPayload: color data tagged with its model, able to convert itself."""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
from numpy.typing import NDArray

from rasl.color.convert.dispatch import convert as _convert_color
from rasl.color.models import MODEL_COMPONENTS
from rasl.color.models import normalize_model as _normalize_color_model
from rasl.signal import FramePayload, MatrixPayload, PayloadCoercionError, PayloadDescriptor, payload


@payload("color")
class ColorPayload(MatrixPayload):
    """Color signal frame with color model tag.
    
    ColorPayload wraps color data with a model tag indicating the color space.
    Use `to_model()` to convert between color spaces.
    
    Shape: [elements, channels] where channels depends on model:
    - srgb, hsl, oklch, oklab, okhsl, okhsv, linear, rec709_rgb_prime: 3 channels
    - rgbw, hsbk: 4 channels
    
    Supported models: srgb (also written rgb), hsl, oklch, oklab, okhsl, okhsv, linear,
    rec709_rgb_prime, rgbw, hsbk
    """

    __slots__ = ("_model", "_encoding")
    domain: ClassVar[str] = "color"
    components: ClassVar[int] = 3
    model_name: ClassVar[str | None] = None

    def __init__(
        self,
        data: NDArray[np.float32],
        model: str,
        encoding: str = "srgb",
    ) -> None:
        arr = np.asarray(data, dtype=np.float32)
        normalized = _normalize_color_model(model)
        # The generic class takes its component count from the model named
        # (rgbw and hsbk have four); a model's own class declares it
        components = MODEL_COMPONENTS.get(normalized) if type(self) is ColorPayload else None
        arr = type(self)._coerce_component_shape(arr, components)
        super().__init__(arr)
        object.__setattr__(self, "_model", normalized)
        object.__setattr__(self, "_encoding", encoding)

    @classmethod
    def coerces_from(cls, other: type) -> bool:
        """The general rule (``FramePayload.coerces_from``), for a type with a model.

        The generic ``ColorPayload`` has no model to give bare data, so nothing coerces
        into it; a concrete color type (``model_name`` set) takes any of its ancestors.
        """
        return cls.model_name is not None and super().coerces_from(other)

    @classmethod
    def coerce(cls, payload: "FramePayload") -> "FramePayload":
        """A matrix, or a generic color of this type's model, as this type.

        Raises:
            PayloadCoercionError: If it is a color of another model (crossing color
                spaces takes a Color node), or the general rule refuses it.
        """
        if isinstance(payload, ColorPayload) and not isinstance(payload, cls):
            if payload.model != cls.model_name:
                raise PayloadCoercionError(
                    f"{type(payload).__name__} of model {payload.model} cannot be made a "
                    f"{cls.__name__} ({cls.model_name}): convert it with a Color node"
                )
        return super().coerce(payload)

    @classmethod
    def _from_data(cls, data: "NDArray[np.float32]") -> "ColorPayload":
        """This concrete color type built from bare data (its own model)."""
        return cls(data)  # type: ignore[call-arg]

    @property
    def model(self) -> str:
        """The normalised color model name of the data, such as 'srgb' or 'oklch'."""
        return self._model

    @property
    def encoding(self) -> str:
        """The encoding tag given at construction, 'srgb' by default.

        A label only: nothing in this class reads it, and conversion ignores it.
        """
        return self._encoding

    def to_model(self, target: type["ColorPayload"]) -> "ColorPayload":
        """Convert to a different color model.

        Type-driven API only: callers must pass a ColorPayload subclass.
        """
        if target is ColorPayload:
            raise TypeError("ColorPayload.to_model() requires a concrete ColorPayload subclass")

        target_model = getattr(target, "model_name", None)
        if not isinstance(target_model, str):
            raise TypeError(
                "ColorPayload.to_model() target must define class var 'model_name: str'"
            )

        target_model = _normalize_color_model(target_model)
        if self._model == target_model and isinstance(self, target):
            return self

        source_components = getattr(type(self), "components", None)
        target_components = getattr(target, "components", None)
        if not isinstance(source_components, int) or source_components <= 0:
            raise ValueError(f"{type(self).__name__} must define 'components' for conversion")
        if not isinstance(target_components, int) or target_components <= 0:
            raise ValueError(f"{target.__name__} must define 'components' for conversion")

        converted = _convert_color(
            self._data,
            self._model,
            target_model,
            source_components=source_components,
            target_components=target_components,
        )

        return target(converted)

    def _channel_view(self, index: int) -> NDArray[np.float32]:
        """One component of every element, as a view: writing to it changes the payload."""
        return self._data[:, index]

    def _set_channel(self, index: int, value: Any) -> None:
        """Set one component of every element, from a scalar or one value per element."""
        self._data[:, index] = np.asarray(value, dtype=np.float32)

    def repeat(self, n: int) -> "ColorPayload":
        """Return the whole frame tiled ``n`` times, end to end.

        Args:
            n: Number of copies. 1 or less returns ``self`` unchanged.

        Returns:
            A payload of the same class, model and encoding with ``count * n`` rows.
        """
        if n <= 1:
            return self
        repeated = np.tile(self._data, (n, 1))
        if type(self) is ColorPayload:
            return ColorPayload(repeated, model=self._model, encoding=self._encoding)
        # A model's own class keeps its type (and its component count)
        try:
            return type(self)(repeated, encoding=self._encoding)  # type: ignore[call-arg]
        except TypeError:
            return type(self)(repeated)  # type: ignore[call-arg]

    def __repr__(self) -> str:
        data = self._data

        def _fmt(v: float) -> str:
            iv = int(v)
            if float(iv) == float(v):
                return str(iv)
            return (f"{float(v):.3f}".rstrip("0").rstrip("."))

        model = self._model
        model_channels = {
            "srgb": 3,
            "rgb": 3,
            "hsl": 3,
            "oklch": 3,
            "oklab": 3,
            "okhsl": 3,
            "okhsv": 3,
            "linear": 3,
            "rec709_rgb_prime": 3,
            "rgbw": 4,
            "hsbk": 4,
        }
        channels_per_pixel = model_channels.get(model)
        if channels_per_pixel is None:
            if data.ndim == 2:
                channels_per_pixel = data.shape[1]
            else:
                channels_per_pixel = 1

        rows: list[list[float]]

        if data.ndim == 2:
            # (count, channels)
            rows = [row.tolist() for row in data]
        else:
            rows = [data.tolist()]

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

        return (
            f"{type(self).__name__}<model={self._model} encoding={self._encoding} "
            f"len={total} data={data_str}>"
        )

    def describe(self) -> PayloadDescriptor:
        """Describe the payload: class name, domain, model, encoding, shape, channels and count."""
        return PayloadDescriptor(
            type_name=type(self).__name__,
            domain=self.domain,
            attrs={
                "model": self._model,
                "encoding": self._encoding,
                "shape": self._data.shape,
                "channels": self.channels,
                "count": self.count,
            },
        )


    @classmethod
    def _coerce_component_shape(
        cls, data: NDArray[np.float32], components: int | None = None
    ) -> NDArray[np.float32]:
        """Ensure incoming data matches this payload's component count.

        Accepts either a flat array (reshaped to [-1, components]) or a matrix
        that already has the correct component dimension. Matrices with a single
        channel are treated as flat data. Any other shape mismatch raises.
        """

        if components is None:
            components = getattr(cls, "components", None)
        if not isinstance(components, int) or components <= 0:
            return data

        if data.ndim == 1:
            total = int(data.size)
            if total % components != 0:
                raise ValueError(
                    f"{cls.__name__} expects data length divisible by {components}, got {total}"
                )
            return data.reshape(-1, components)

        if data.ndim != 2:
            raise ValueError(f"{cls.__name__} requires 1D or 2D data, got shape {data.shape!r}")

        channels = data.shape[1]
        if channels == components:
            return data

        if channels == 1:
            rows = int(data.shape[0])
            if rows % components != 0:
                raise ValueError(
                    f"{cls.__name__} cannot reshape data with {rows} rows into {components}-component elements"
                )
            return data.reshape(-1, components)

        raise ValueError(
            f"{cls.__name__} expects data with {components} components per element, "
            f"got {channels}"
        )
