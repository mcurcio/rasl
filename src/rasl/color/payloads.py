"""Color payload types for color signal data.

This module defines the color model-specific subclasses of ColorPayload
(RGB, HSL, OKLCH, Oklab, OkHSL, OkHSV, Linear RGB, Rec.709 R′G′B′).
"""

from __future__ import annotations

from typing import Any, ClassVar, Type

import numpy as np
from numpy.typing import NDArray

from rasl.color.base import ColorPayload
from rasl.signal import FramePayload, MatrixPayload, payload


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
        """Hue, 0 to 1 (column 0), one value per element."""
        return self._channel_view(0)

    @hue.setter
    def hue(self, value: Any) -> None:
        self._set_channel(0, value)

    @property
    def saturation(self) -> NDArray[np.float32]:
        """Saturation, 0 to 1 (column 1), one value per element."""
        return self._channel_view(1)

    @saturation.setter
    def saturation(self, value: Any) -> None:
        self._set_channel(1, value)

    @property
    def brightness(self) -> NDArray[np.float32]:
        """Brightness, 0 to 1 (column 2), one value per element."""
        return self._channel_view(2)

    @brightness.setter
    def brightness(self, value: Any) -> None:
        self._set_channel(2, value)

    @property
    def kelvin(self) -> NDArray[np.float32]:
        """Color temperature (column 3), 0 to 1 across 1500 K to 9000 K, one value per element."""
        return self._channel_view(3)

    @kelvin.setter
    def kelvin(self, value: Any) -> None:
        self._set_channel(3, value)

    @classmethod
    def is_compatible_with(cls, other: Type[FramePayload]) -> bool:
        """HsbkColorPayload accepts any MatrixPayload."""
        return issubclass(other, MatrixPayload)

@payload("color:rgb")
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
        """Red, 0 to 1 (column 0), one value per element."""
        return self._channel_view(0)

    @red.setter
    def red(self, value: Any) -> None:
        self._set_channel(0, value)

    @property
    def green(self) -> NDArray[np.float32]:
        """Green, 0 to 1 (column 1), one value per element."""
        return self._channel_view(1)

    @green.setter
    def green(self, value: Any) -> None:
        self._set_channel(1, value)

    @property
    def blue(self) -> NDArray[np.float32]:
        """Blue, 0 to 1 (column 2), one value per element."""
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
        """White, 0 to 1 (column 3), one value per element."""
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
        """Hue, 0 to 1 (column 0), one value per element."""
        return self._channel_view(0)

    @hue.setter
    def hue(self, value: Any) -> None:
        self._set_channel(0, value)

    @property
    def saturation(self) -> NDArray[np.float32]:
        """Saturation, 0 to 1 (column 1), one value per element."""
        return self._channel_view(1)

    @saturation.setter
    def saturation(self, value: Any) -> None:
        self._set_channel(1, value)

    @property
    def lightness(self) -> NDArray[np.float32]:
        """Lightness, 0 to 1 (column 2), one value per element."""
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
