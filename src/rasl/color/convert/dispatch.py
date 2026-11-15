"""Converting pixels from one color model to another.

``convert`` picks a direct conversion where there is one and goes through CIE XYZ
otherwise. The conversions themselves are in this package, one module per
family of models.
"""

from __future__ import annotations

import colour
import numpy as np
from numpy.typing import NDArray

from rasl.color.convert.hsbk import _hsbk_to_srgb, _srgb_to_hsbk
from rasl.color.convert.hsl import _hsl_to_srgb, _srgb_to_hsl
from rasl.color.convert.okhsx import _okhsl_to_srgb, _okhsv_to_srgb, _srgb_to_okhsl, _srgb_to_okhsv
from rasl.color.convert.oklab import (
    _oklab_to_oklch,
    _oklab_to_srgb_direct,
    _oklch_to_oklab,
    _srgb_to_oklab_direct,
)
from rasl.color.convert.rgb import (
    _linear_to_rec709_rgb_prime,
    _linear_to_srgb,
    _rec709_rgb_prime_to_linear,
    _rgbw_to_srgb,
    _srgb_to_linear,
    _srgb_to_rgbw,
)
from rasl.color.models import _resolve_components, normalize_model

colour.utilities.filter_warnings(colour_usage_warnings=False)


def _clip_to_model(result: NDArray, model: str) -> NDArray:
    """Keep a converted result inside its model's range.

    Every model's components run from 0 to 1 except Oklab's a and b, which are
    signed (green to red, blue to yellow): only its lightness is clipped.
    """
    if model == "oklab":
        clipped = np.array(result, dtype=np.float32)
        clipped[..., 0] = np.clip(clipped[..., 0], 0.0, 1.0)
        return clipped
    return np.clip(result, 0.0, 1.0)


def convert(
    data: NDArray[np.float32],
    from_model: str,
    to_model: str,
    *,
    source_components: int | None = None,
    target_components: int | None = None,
) -> NDArray[np.float32]:
    """Convert color data from one model to another.

    A pair with a direct conversion uses it; HSBK goes through sRGB; any other
    pair goes through CIE XYZ. Results are clipped to 0..1 (Oklab keeps signed a
    and b), except on the HSBK paths, whose conversions clip for themselves.

    Args:
        data: One row per element and one column per component, or a flat array
            whose length is a multiple of the source component count.
        from_model: Source model name or alias (see ``normalize_model``).
        to_model: Target model name or alias.
        source_components: Components per element in ``data``; the model's own
            count when None.
        target_components: Components per element in the result; the model's own
            count when None.

    Returns:
        A float32 array of shape (count, target_components). When the two models
        are the same, ``data`` itself, unchanged and unchecked.

    Raises:
        ValueError: If a model is unknown, a component override is not positive,
            or the shape of ``data`` does not match the source component count.
    """
    from_model = normalize_model(from_model)
    to_model = normalize_model(to_model)

    if from_model == to_model:
        return data

    source_components = _resolve_components(from_model, source_components)
    target_components = _resolve_components(to_model, target_components)

    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim == 1:
        total = int(arr.size)
        if total % source_components != 0:
            raise ValueError(
                f"Color data must have length divisible by {source_components}, got {total} values."
            )
        pixels = arr.reshape(-1, source_components)
    elif arr.ndim == 2:
        channels = arr.shape[1]
        if channels != source_components:
            raise ValueError(
                f"Expected data with {source_components} components per element, got {channels}"
            )
        pixels = arr
    else:
        raise ValueError(f"Color data must be 1D or 2D, got shape {arr.shape!r}")

    count = pixels.shape[0]

    if from_model == "hsbk":
        srgb_pixels = _hsbk_to_srgb(pixels)
        if to_model == "hsbk":
            return pixels.reshape(count, target_components).astype(np.float32)
        if to_model == "srgb":
            return srgb_pixels.reshape(count, target_components).astype(np.float32)
        if to_model == "rgbw":
            rgbw = _srgb_to_rgbw(srgb_pixels)
            return rgbw.reshape(count, target_components).astype(np.float32)
        converted = convert(
            srgb_pixels,
            "srgb",
            to_model,
            source_components=3,
            target_components=target_components,
        )
        return converted

    if to_model == "hsbk":
        if from_model == "hsbk":
            return pixels.reshape(count, target_components).astype(np.float32)
        if from_model == "srgb":
            srgb_pixels = pixels
        elif from_model == "rgbw":
            srgb_pixels = _rgbw_to_srgb(pixels)
        else:
            srgb_pixels = convert(
                pixels,
                from_model,
                "srgb",
                source_components=source_components,
                target_components=3,
            )
        result = _srgb_to_hsbk(srgb_pixels)
        return result.reshape(count, target_components).astype(np.float32)

    result = _try_direct_convert(pixels, from_model, to_model)
    if result is not None:
        result = _clip_to_model(result, to_model)
        return result.reshape(count, target_components).astype(np.float32)

    xyz = _to_xyz(pixels, from_model)
    result = _from_xyz(xyz, to_model)

    result = _clip_to_model(result, to_model)
    return result.reshape(count, target_components).astype(np.float32)


def _try_direct_convert(
    data: NDArray,
    from_model: str,
    to_model: str,
) -> NDArray | None:
    """Convert with the hand-written conversion for this pair of models; None if there is none."""
    if from_model == "okhsl" and to_model == "srgb":
        return _okhsl_to_srgb(data)
    if from_model == "srgb" and to_model == "okhsl":
        return _srgb_to_okhsl(data)

    if from_model == "okhsv" and to_model == "srgb":
        return _okhsv_to_srgb(data)
    if from_model == "srgb" and to_model == "okhsv":
        return _srgb_to_okhsv(data)

    if from_model == "oklab" and to_model == "srgb":
        return _oklab_to_srgb_direct(data)
    if from_model == "srgb" and to_model == "oklab":
        return _srgb_to_oklab_direct(data)

    if from_model == "hsl" and to_model == "srgb":
        return _hsl_to_srgb(data)
    if from_model == "srgb" and to_model == "hsl":
        return _srgb_to_hsl(data)

    if from_model == "oklch" and to_model == "oklab":
        return _oklch_to_oklab(data)
    if from_model == "oklab" and to_model == "oklch":
        return _oklab_to_oklch(data)

    if from_model == "oklch" and to_model == "srgb":
        oklab = _oklch_to_oklab(data)
        return _oklab_to_srgb_direct(oklab)
    if from_model == "srgb" and to_model == "oklch":
        oklab = _srgb_to_oklab_direct(data)
        return _oklab_to_oklch(oklab)

    if from_model == "linear" and to_model == "srgb":
        return _linear_to_srgb(data)
    if from_model == "srgb" and to_model == "linear":
        return _srgb_to_linear(data)

    if from_model == "linear" and to_model == "rec709_rgb_prime":
        return _linear_to_rec709_rgb_prime(data)
    if from_model == "rec709_rgb_prime" and to_model == "linear":
        return _rec709_rgb_prime_to_linear(data)

    return None


def _to_xyz(data: NDArray, model: str) -> NDArray:
    """Convert pixels of any model but HSBK to CIE XYZ. Raises ValueError for an unknown model."""
    match model:
        case "srgb":
            return colour.sRGB_to_XYZ(data)
        case "rgbw":
            return colour.sRGB_to_XYZ(_rgbw_to_srgb(data))
        case "linear":
            return colour.RGB_to_XYZ(data, "sRGB")
        case "rec709_rgb_prime":
            linear = _rec709_rgb_prime_to_linear(data)
            return colour.RGB_to_XYZ(linear, "sRGB")
        case "oklab":
            return colour.Oklab_to_XYZ(data)
        case "oklch":
            oklab = _oklch_to_oklab(data)
            return colour.Oklab_to_XYZ(oklab)
        case "hsl":
            rgb = _hsl_to_srgb(data)
            return colour.sRGB_to_XYZ(rgb)
        case "okhsl":
            rgb = _okhsl_to_srgb(data)
            return colour.sRGB_to_XYZ(rgb)
        case "okhsv":
            rgb = _okhsv_to_srgb(data)
            return colour.sRGB_to_XYZ(rgb)
        case _:
            raise ValueError(f"Unknown color model: {model}")


def _from_xyz(xyz: NDArray, model: str) -> NDArray:
    """Convert CIE XYZ pixels to any model but HSBK. Raises ValueError for an unknown model."""
    match model:
        case "srgb":
            return colour.XYZ_to_sRGB(xyz)
        case "rgbw":
            srgb = colour.XYZ_to_sRGB(xyz)
            return _srgb_to_rgbw(srgb)
        case "linear":
            return colour.XYZ_to_RGB(xyz, "sRGB")
        case "rec709_rgb_prime":
            linear = colour.XYZ_to_RGB(xyz, "sRGB")
            return _linear_to_rec709_rgb_prime(linear)
        case "oklab":
            return colour.XYZ_to_Oklab(xyz)
        case "oklch":
            oklab = colour.XYZ_to_Oklab(xyz)
            return _oklab_to_oklch(oklab)
        case "hsl":
            rgb = colour.XYZ_to_sRGB(xyz)
            return _srgb_to_hsl(rgb)
        case "okhsl":
            rgb = colour.XYZ_to_sRGB(xyz)
            return _srgb_to_okhsl(rgb)
        case "okhsv":
            rgb = colour.XYZ_to_sRGB(xyz)
            return _srgb_to_okhsv(rgb)
        case _:
            raise ValueError(f"Unknown color model: {model}")
