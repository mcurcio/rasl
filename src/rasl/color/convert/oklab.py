"""Oklab and Oklch.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def _oklab_to_oklch(oklab: NDArray) -> NDArray:
    l = oklab[..., 0]
    a = oklab[..., 1]
    b = oklab[..., 2]

    c = np.sqrt(a**2 + b**2)
    h = np.arctan2(b, a) / (2 * np.pi)
    h = np.mod(h, 1.0)

    return np.stack([l, c, h], axis=-1)


def _oklch_to_oklab(oklch: NDArray) -> NDArray:
    l = oklch[..., 0]
    c = oklch[..., 1]
    h = oklch[..., 2]

    h_rad = h * 2 * np.pi
    a = c * np.cos(h_rad)
    b = c * np.sin(h_rad)

    return np.stack([l, a, b], axis=-1)


def _srgb_to_oklab_direct(rgb: NDArray) -> NDArray:
    linear = np.where(
        rgb <= 0.04045,
        rgb / 12.92,
        np.power((rgb + 0.055) / 1.055, 2.4),
    )

    r = linear[..., 0]
    g = linear[..., 1]
    b = linear[..., 2]

    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

    l_ = np.cbrt(l)
    m_ = np.cbrt(m)
    s_ = np.cbrt(s)

    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b_out = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_

    return np.stack([L, a, b_out], axis=-1)


def _oklab_to_srgb_direct(oklab: NDArray) -> NDArray:
    L = oklab[..., 0]
    a = oklab[..., 1]
    b = oklab[..., 2]

    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b

    l = l_**3
    m = m_**3
    s = s_**3

    r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b_out = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    linear = np.stack([r, g, b_out], axis=-1)

    rgb = np.where(
        linear <= 0.0031308,
        12.92 * linear,
        1.055 * np.power(np.maximum(linear, 0), 1 / 2.4) - 0.055,
    )

    return np.clip(rgb, 0, 1)


def _oklab_to_linear_rgb(oklab: NDArray) -> NDArray:
    L = oklab[..., 0]
    a = oklab[..., 1]
    b = oklab[..., 2]

    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b

    l = l_**3
    m = m_**3
    s = s_**3

    r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b_out = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    return np.stack([r, g, b_out], axis=-1)
