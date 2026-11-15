"""HSBK (hue, saturation, brightness, kelvin), to and from sRGB.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from rasl.color.convert.hsl import _hsv_to_srgb, _srgb_to_hsv

_MIN_KELVIN = 1500.0
_MAX_KELVIN = 9000.0
_DEFAULT_KELVIN = 6500.0
_KELVIN_RANGE = _MAX_KELVIN - _MIN_KELVIN


def _normalize_kelvin_channel(kelvin: NDArray | float) -> NDArray | float:
    """Map kelvin to 0..1 across 1500 K to 9000 K, clipping outside that range."""
    return np.clip((kelvin - _MIN_KELVIN) / _KELVIN_RANGE, 0.0, 1.0)


def _denormalize_kelvin_channel(channel: NDArray | float) -> NDArray | float:
    """Map a 0..1 kelvin channel (clipped) back to kelvin, 1500 K to 9000 K."""
    return np.clip(channel, 0.0, 1.0) * _KELVIN_RANGE + _MIN_KELVIN


def _kelvin_to_srgb_white(kelvin: NDArray | float) -> NDArray:
    """Approximate the sRGB color, (..., 3) in 0..1, of white at a temperature in kelvin.

    The temperature is clipped to 1500..9000 K. The input must be a NumPy array or scalar.
    """
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


_NEUTRAL_KELVIN = 6600.0
"""The temperature whose white is (1, 1, 1): at it, HSBK is plain HSV."""

_KELVIN_GRID = np.linspace(_MIN_KELVIN, _MAX_KELVIN, 151)
"""The temperatures ``_srgb_to_hsbk`` chooses from, 50 K apart (6600 K is one of them).
Finer costs time (about 10 ms for 512 pixels at this spacing); coarser leaves a white
between two grid temperatures visibly tinted."""


def _srgb_to_hsbk(srgb: NDArray) -> NDArray:
    """Convert sRGB (..., 3) to float32 HSBK so that ``_hsbk_to_srgb`` gives the color back.

    HSBK describes a color as white light of temperature K plus a fully
    saturated hue: ``rgb = B * (1 - S) * white(K) + B * S * hue(H)``. Three
    numbers cannot fix four, so one rule picks among the descriptions of a
    color: use as much white as possible, at whatever temperature allows the
    most, and the hue for the rest. A warm white comes out as S = 0 at its
    temperature, not as a pale orange at a neutral one. Where the temperature
    makes no difference (a fully saturated color has no white), it is the
    neutral 6600 K.

    The round trip sRGB -> HSBK -> sRGB is exact. HSBK -> sRGB -> HSBK gives an
    HSBK of the same color, which is the original only when the original
    followed the same rule: K is recovered for whites, and H, S and B for
    colors whose white share is already as large as it can be.
    """
    rgb = np.clip(np.asarray(srgb, dtype=np.float64), 0.0, 1.0)
    shape = rgb.shape[:-1]
    rgb = rgb.reshape(-1, 3)
    whites = _kelvin_to_srgb_white(_KELVIN_GRID).astype(np.float64)  # (grid, 3)

    # For each temperature: the most of its white the color holds, and what is left over
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(whites[None] > 1e-6, rgb[:, None, :] / whites[None], np.inf)
    white_share = ratio.min(axis=-1)  # (pixels, grid)
    rest = np.clip(rgb[:, None, :] - white_share[..., None] * whites[None], 0.0, None)
    hue_share = rest.max(axis=-1)

    # Most white, among the temperatures that keep brightness within 1 (6600 K
    # always does); on a tie, the temperature nearest neutral
    score = np.where(white_share + hue_share <= 1.0 + 1e-6, white_share, -1.0)
    best = score.max(axis=1, keepdims=True)
    distance = np.where(score >= best - 1e-6, np.abs(_KELVIN_GRID[None] - _NEUTRAL_KELVIN), np.inf)
    chosen = distance.argmin(axis=1)
    rows = np.arange(rgb.shape[0])
    white_share = white_share[rows, chosen]
    rest = rest[rows, chosen]
    hue_share = hue_share[rows, chosen]

    brightness = white_share + hue_share
    saturation = np.where(brightness > 1e-9, hue_share / np.maximum(brightness, 1e-9), 0.0)
    pure = np.where(hue_share[:, None] > 1e-9, rest / np.maximum(hue_share[:, None], 1e-9), 0.0)
    hue = _srgb_to_hsv(pure)[..., 0]
    kelvin = _normalize_kelvin_channel(_KELVIN_GRID[chosen])

    hsbk = np.stack([hue, saturation, np.clip(brightness, 0.0, 1.0), kelvin], axis=-1)
    return hsbk.reshape(*shape, 4).astype(np.float32)


def _hsbk_to_srgb(hsbk: NDArray) -> NDArray:
    """Convert HSBK (..., 4), components clipped to 0..1, to sRGB (..., 3) in 0..1.

    The HSV color is shifted toward the kelvin white in proportion to 1 - S, so
    K has full effect on white and none on a fully saturated color.
    """
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
