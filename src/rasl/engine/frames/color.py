"""Color payload types for color signal data.

This module defines ColorPayload and all color model-specific subclasses
(RGB, HSL, OKLCH, Oklab, OkHSL, OkHSV, Linear RGB, Rec.709 R′G′B′).
"""

from __future__ import annotations

from typing import Any, ClassVar, Type

import numpy as np
from numpy.typing import NDArray

from .base import FramePayload, PayloadDescriptor
from .matrix import MatrixPayload
from ..registry import payload
from .._color_convert import convert as _convert_color
from .._color_convert import normalize_model as _normalize_color_model


@payload("color")
class ColorPayload(MatrixPayload):
    """Color signal frame with color model tag.
    
    ColorPayload wraps color data with a model tag indicating the color space.
    Use `to_model()` to convert between color spaces.
    
    Shape: [elements, channels] where channels depends on model:
    - rgb, srgb, hsl, oklch, oklab, okhsl, okhsv, linear, rec709_rgb_prime: 3 channels
    - rgbw, hsbk: 4 channels
    
    Supported models: srgb, rgb, hsl, oklch, oklab, okhsl, okhsv, linear, rec709_rgb_prime, hsbk
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
        arr = type(self)._coerce_component_shape(arr)
        super().__init__(arr)
        object.__setattr__(self, "_model", _normalize_color_model(model))
        object.__setattr__(self, "_encoding", encoding)

    @property
    def model(self) -> str:
        return self._model

    @property
    def encoding(self) -> str:
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

    def repeat(self, n: int) -> "ColorPayload":
        if n <= 1:
            return self
        repeated = np.tile(self._data, (n, 1))
        return ColorPayload(repeated, model=self._model, encoding=self._encoding)

    def describe(self) -> PayloadDescriptor:
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
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """ColorPayload accepts any MatrixPayload (will be tagged/converted)."""
        return issubclass(other, MatrixPayload)

    @classmethod
    def _coerce_component_shape(cls, data: NDArray[np.float32]) -> NDArray[np.float32]:
        """Ensure incoming data matches this payload's component count.

        Accepts either a flat array (reshaped to [-1, components]) or a matrix
        that already has the correct component dimension. Matrices with a single
        channel are treated as flat data. Any other shape mismatch raises.
        """

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


@payload("color:hsbk")
class HsbkColorPayload(ColorPayload):
    """HSBK color frame for LIFX-compatible hue/sat/brightness/kelvin data.

    Components (normalized 0–1 unless noted):
        H: Hue
        S: Saturation
        B: Brightness/value
        K: Kelvin normalized to the 1500K–9000K LIFX range
    """

    __slots__ = ()
    components: ClassVar[int] = 4
    model_name: ClassVar[str] = "hsbk"

    def __init__(self, data: NDArray[np.float32], encoding: str = "hsbk") -> None:
        super().__init__(data, model="hsbk", encoding=encoding)

    @property
    def hue(self) -> NDArray[np.float32]:
        return self._channel_view(0)

    @hue.setter
    def hue(self, value: Any) -> None:
        self._set_channel(0, value)

    @property
    def saturation(self) -> NDArray[np.float32]:
        return self._channel_view(1)

    @saturation.setter
    def saturation(self, value: Any) -> None:
        self._set_channel(1, value)

    @property
    def brightness(self) -> NDArray[np.float32]:
        return self._channel_view(2)

    @brightness.setter
    def brightness(self, value: Any) -> None:
        self._set_channel(2, value)

    @property
    def kelvin(self) -> NDArray[np.float32]:
        return self._channel_view(3)

    @kelvin.setter
    def kelvin(self, value: Any) -> None:
        self._set_channel(3, value)

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        return issubclass(other, MatrixPayload)


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
            f"ColorPayload<model={self._model} encoding={self._encoding} "
            f"len={total} data={data_str}>"
        )

@payload("color:srgb")
class RgbColorPayload(ColorPayload):
    """sRGB color frame."""

    __slots__ = ()
    components: ClassVar[int] = 3
    model_name: ClassVar[str] = "srgb"

    def __init__(self, data: NDArray[np.float32], encoding: str = "srgb") -> None:
        super().__init__(data, model="srgb", encoding=encoding)

    @property
    def red(self) -> NDArray[np.float32]:
        return self._channel_view(0)

    @red.setter
    def red(self, value: Any) -> None:
        self._set_channel(0, value)

    @property
    def green(self) -> NDArray[np.float32]:
        return self._channel_view(1)

    @green.setter
    def green(self, value: Any) -> None:
        self._set_channel(1, value)

    @property
    def blue(self) -> NDArray[np.float32]:
        return self._channel_view(2)

    @blue.setter
    def blue(self, value: Any) -> None:
        self._set_channel(2, value)

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """RgbColorPayload accepts any MatrixPayload."""
        return issubclass(other, MatrixPayload)


@payload("color:rgbw")
class RgbwColorPayload(ColorPayload):
    """RGBW color frame with dedicated white channel."""

    __slots__ = ()
    components: ClassVar[int] = 4
    model_name: ClassVar[str] = "rgbw"

    def __init__(self, data: NDArray[np.float32], encoding: str = "srgb") -> None:
        super().__init__(data, model="rgbw", encoding=encoding)

    @property
    def white(self) -> NDArray[np.float32]:
        return self._channel_view(3)

    @white.setter
    def white(self, value: Any) -> None:
        self._set_channel(3, value)


@payload("color:hsl")
class HslColorPayload(ColorPayload):
    """HSL color frame."""

    __slots__ = ()
    components: ClassVar[int] = 3
    model_name: ClassVar[str] = "hsl"

    def __init__(self, data: NDArray[np.float32], encoding: str = "srgb") -> None:
        super().__init__(data, model="hsl", encoding=encoding)

    @property
    def hue(self) -> NDArray[np.float32]:
        return self._channel_view(0)

    @hue.setter
    def hue(self, value: Any) -> None:
        self._set_channel(0, value)

    @property
    def saturation(self) -> NDArray[np.float32]:
        return self._channel_view(1)

    @saturation.setter
    def saturation(self, value: Any) -> None:
        self._set_channel(1, value)

    @property
    def lightness(self) -> NDArray[np.float32]:
        return self._channel_view(2)

    @lightness.setter
    def lightness(self, value: Any) -> None:
        self._set_channel(2, value)

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """HslColorPayload accepts any MatrixPayload."""
        return issubclass(other, MatrixPayload)


@payload("color:oklch")
class OklchColorPayload(ColorPayload):
    """OKLCH color frame - perceptually uniform cylindrical space.

    OKLCH is the recommended internal color model for animation and mixing
    due to its perceptual uniformity. Components are:
    - L: Lightness [0, 1]
    - C: Chroma (saturation) [0, ~0.4 for sRGB gamut]
    - H: Hue [0, 1] (normalized, not degrees)
    """

    __slots__ = ()
    components: ClassVar[int] = 3
    model_name: ClassVar[str] = "oklch"

    def __init__(self, data: NDArray[np.float32], encoding: str = "srgb") -> None:
        super().__init__(data, model="oklch", encoding=encoding)

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """OklchColorPayload accepts any MatrixPayload."""
        return issubclass(other, MatrixPayload)


@payload("color:oklab")
class OklabColorPayload(ColorPayload):
    """Oklab color frame - perceptually uniform cartesian space.

    Oklab is the cartesian form of OKLCH. Components are:
    - L: Lightness [0, 1]
    - a: Green-red axis [-0.4, 0.4]
    - b: Blue-yellow axis [-0.4, 0.4]
    """

    __slots__ = ()
    components: ClassVar[int] = 3
    model_name: ClassVar[str] = "oklab"

    def __init__(self, data: NDArray[np.float32], encoding: str = "srgb") -> None:
        super().__init__(data, model="oklab", encoding=encoding)

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """OklabColorPayload accepts any MatrixPayload."""
        return issubclass(other, MatrixPayload)


@payload("color:okhsl")
class OkhslColorPayload(ColorPayload):
    """OkHSL color frame - perceptually uniform HSL-like space.

    OkHSL is based on Oklab and provides uniform hue perception.
    Better than OKLCH for hue-based animations. Components are:
    - H: Hue [0, 1] (normalized, not degrees)
    - S: Saturation [0, 1]
    - L: Lightness [0, 1]
    """

    __slots__ = ()
    components: ClassVar[int] = 3
    model_name: ClassVar[str] = "okhsl"

    def __init__(self, data: NDArray[np.float32], encoding: str = "srgb") -> None:
        super().__init__(data, model="okhsl", encoding=encoding)

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """OkhslColorPayload accepts any MatrixPayload."""
        return issubclass(other, MatrixPayload)


@payload("color:okhsv")
class OkhsvColorPayload(ColorPayload):
    """OkHSV color frame - perceptually uniform HSV-like space.

    OkHSV is based on Oklab and provides uniform hue perception.
    Better than OKLCH for hue-based animations. Components are:
    - H: Hue [0, 1] (normalized, not degrees)
    - S: Saturation [0, 1]
    - V: Value (brightness) [0, 1]
    """

    __slots__ = ()
    components: ClassVar[int] = 3
    model_name: ClassVar[str] = "okhsv"

    def __init__(self, data: NDArray[np.float32], encoding: str = "srgb") -> None:
        super().__init__(data, model="okhsv", encoding=encoding)

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """OkhsvColorPayload accepts any MatrixPayload."""
        return issubclass(other, MatrixPayload)


@payload("color:linear")
class LinearRgbColorPayload(ColorPayload):
    """Linear RGB color frame - no gamma encoding.

    Linear RGB is the raw, physically linear color space before
    gamma encoding is applied. Useful for:
    - Physically correct blending and compositing
    - Color correction operations
    - Converting to/from sRGB for display

    Components are R, G, B in [0, 1] range (linear light).
    """

    __slots__ = ()
    components: ClassVar[int] = 3
    model_name: ClassVar[str] = "linear"

    def __init__(self, data: NDArray[np.float32], encoding: str = "linear") -> None:
        super().__init__(data, model="linear", encoding=encoding)

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """LinearRgbColorPayload accepts any MatrixPayload."""
        return issubclass(other, MatrixPayload)


@payload("color:rec709_rgb_prime")
class Rec709RgbPrimeColorPayload(ColorPayload):
    """Rec.709 R′G′B′ color frame with limited-range scaling.

    Values represent normalized digital video levels (0 ↔ code 0, 1 ↔ code 255).
    The active video range (code values 16–235) is automatically scaled to [0, 1]
    before the Rec.709 opto-electronic transfer function is applied, and scaled
    back when converting from linear light.
    """

    __slots__ = ()
    components: ClassVar[int] = 3
    model_name: ClassVar[str] = "rec709_rgb_prime"

    def __init__(self, data: NDArray[np.float32], encoding: str = "rec709_rgb_prime") -> None:
        super().__init__(data, model="rec709_rgb_prime", encoding=encoding)

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """Rec709RgbPrimeColorPayload accepts any MatrixPayload."""
        return issubclass(other, MatrixPayload)
