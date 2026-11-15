"""RGB encodings: sRGB and linear light, Rec. 709 video levels, RGBW.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def _srgb_to_linear(rgb: NDArray) -> NDArray:
    return np.where(
        rgb <= 0.04045,
        rgb / 12.92,
        np.power((rgb + 0.055) / 1.055, 2.4),
    ).astype(np.float32)


def _linear_to_srgb(linear: NDArray) -> NDArray:
    return np.where(
        linear <= 0.0031308,
        12.92 * linear,
        1.055 * np.power(np.maximum(linear, 0), 1 / 2.4) - 0.055,
    ).astype(np.float32)


_REC709_LEVEL_MIN = 16.0 / 255.0
_REC709_LEVEL_MAX = 235.0 / 255.0
_REC709_LEVEL_RANGE = _REC709_LEVEL_MAX - _REC709_LEVEL_MIN


def _rec709_video_to_encoded(rgb: NDArray) -> NDArray:
    """Map normalized video levels (0-1 == code 0-255) to encoded Rec.709 R′."""
    encoded = (rgb - _REC709_LEVEL_MIN) / _REC709_LEVEL_RANGE
    return np.clip(encoded, 0.0, 1.0)


def _encoded_to_rec709_video(encoded: NDArray) -> NDArray:
    """Map encoded Rec.709 R′ in [0,1] back to normalized video levels."""
    video = encoded * _REC709_LEVEL_RANGE + _REC709_LEVEL_MIN
    return np.clip(video, 0.0, 1.0)


def _rec709_gamma_to_linear(rgb_prime: NDArray) -> NDArray:
    return np.where(
        rgb_prime <= 0.081,
        rgb_prime / 4.5,
        np.power((rgb_prime + 0.099) / 1.099, 1 / 0.45),
    ).astype(np.float32)


def _linear_to_rec709_gamma(linear: NDArray) -> NDArray:
    linear = np.clip(linear, 0.0, 1.0)
    return np.where(
        linear <= 0.018,
        4.5 * linear,
        1.099 * np.power(np.maximum(linear, 0), 0.45) - 0.099,
    ).astype(np.float32)


def _rec709_rgb_prime_to_linear(rgb: NDArray) -> NDArray:
    encoded = _rec709_video_to_encoded(rgb)
    return _rec709_gamma_to_linear(encoded)


def _linear_to_rec709_rgb_prime(linear: NDArray) -> NDArray:
    encoded = _linear_to_rec709_gamma(linear)
    return _encoded_to_rec709_video(encoded)


def _rgbw_to_srgb(data: NDArray) -> NDArray:
    return data[..., :3]


def _srgb_to_rgbw(data: NDArray) -> NDArray:
    zeros = np.zeros((*data.shape[:-1], 1), dtype=np.float32)
    return np.concatenate([data, zeros], axis=-1)
