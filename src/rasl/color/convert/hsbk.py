"""HSBK (hue, saturation, brightness, kelvin), to and from sRGB.
"""

from __future__ import annotations

import colour
import numpy as np
from numpy.typing import NDArray

from rasl.color.convert.hsl import _hsv_to_srgb, _srgb_to_hsv

_MIN_KELVIN = 1500.0
_MAX_KELVIN = 9000.0
_DEFAULT_KELVIN = 6500.0
_KELVIN_RANGE = _MAX_KELVIN - _MIN_KELVIN


def _normalize_kelvin_channel(kelvin: NDArray | float) -> NDArray | float:
    return np.clip((kelvin - _MIN_KELVIN) / _KELVIN_RANGE, 0.0, 1.0)


def _denormalize_kelvin_channel(channel: NDArray | float) -> NDArray | float:
    return np.clip(channel, 0.0, 1.0) * _KELVIN_RANGE + _MIN_KELVIN


def _estimate_kelvin_from_srgb(rgb: NDArray) -> NDArray:
    rgb = np.clip(rgb, 1e-5, 1.0).astype(np.float64)
    
    # Ensure rgb is at least 2D for colour library compatibility
    original_shape = rgb.shape
    if rgb.ndim == 1:
        rgb = rgb.reshape(1, -1)
    
    xyz = colour.sRGB_to_XYZ(rgb)
    xyY = colour.XYZ_to_xyY(xyz)
    x = xyY[..., 0]
    y = xyY[..., 1]

    denom = y - 0.1858
    valid = np.abs(denom) > 1e-6
    n = np.where(valid, (x - 0.3320) / denom, 0.0)

    kelvin = -449.0 * n**3 + 3525.0 * n**2 - 6823.3 * n + 5520.33
    kelvin = np.where(valid, kelvin, _DEFAULT_KELVIN)
    kelvin = np.where(np.isfinite(kelvin), kelvin, _DEFAULT_KELVIN)
    kelvin = np.clip(kelvin, _MIN_KELVIN, _MAX_KELVIN)
    
    # Restore original shape if needed
    if len(original_shape) == 1:
        kelvin = kelvin.ravel()
    
    return kelvin.astype(np.float32)


def _kelvin_to_srgb_white(kelvin: NDArray | float) -> NDArray:
    kelvin = np.clip(kelvin, _MIN_KELVIN, _MAX_KELVIN).astype(np.float64) / 100.0

    def clamp(v: NDArray) -> NDArray:
        return np.clip(v, 0.0, 255.0)

    red = np.where(
        kelvin <= 66.0,
        255.0,
        clamp(329.698727446 * np.power(np.maximum(kelvin - 60.0, 1e-3), -0.1332047592)),
    )

    green = np.where(
        kelvin <= 66.0,
        clamp(99.4708025861 * np.log(np.maximum(kelvin, 1e-3)) - 161.1195681661),
        clamp(288.1221695283 * np.power(np.maximum(kelvin - 60.0, 1e-3), -0.0755148492)),
    )

    blue = np.where(
        kelvin >= 66.0,
        255.0,
        np.where(
            kelvin <= 19.0,
            0.0,
            clamp(138.5177312231 * np.log(np.maximum(kelvin - 10.0, 1e-3)) - 305.0447927307),
        ),
    )

    rgb = np.stack([red, green, blue], axis=-1) / 255.0
    return np.clip(rgb, 0.0, 1.0).astype(np.float32)


def _srgb_to_hsbk(srgb: NDArray) -> NDArray:
    hsv = _srgb_to_hsv(srgb)
    kelvin = _estimate_kelvin_from_srgb(srgb)
    normalized_kelvin = _normalize_kelvin_channel(kelvin)
    return np.concatenate([hsv, normalized_kelvin[..., None]], axis=-1).astype(np.float32)


def _hsbk_to_srgb(hsbk: NDArray) -> NDArray:
    h = np.clip(hsbk[..., 0], 0.0, 1.0)
    s = np.clip(hsbk[..., 1], 0.0, 1.0)
    v = np.clip(hsbk[..., 2], 0.0, 1.0)
    kelvin = _denormalize_kelvin_channel(hsbk[..., 3])

    hsv = np.stack([h, s, v], axis=-1)
    rgb = _hsv_to_srgb(hsv).astype(np.float64)

    neutral = np.stack([v, v, v], axis=-1)
    kelvin_white = _kelvin_to_srgb_white(kelvin) * v[..., None]
    blend = (1.0 - s)[..., None]
    tinted = rgb + (kelvin_white - neutral) * blend
    return np.clip(tinted, 0.0, 1.0).astype(np.float32)
