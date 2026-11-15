"""HSL and HSV, to and from sRGB.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def _hsl_to_srgb(hsl: NDArray) -> NDArray:
    h = hsl[..., 0]
    s = hsl[..., 1]
    l = hsl[..., 2]

    rgb = np.zeros((*hsl.shape[:-1], 3), dtype=np.float64)

    q = np.where(l < 0.5, l * (1.0 + s), l + s - l * s)
    p = 2.0 * l - q

    def hue_to_rgb(p: NDArray, q: NDArray, t: NDArray) -> NDArray:
        t = np.mod(t, 1.0)
        result = np.empty_like(t)
        mask1 = t < 1 / 6
        mask2 = (~mask1) & (t < 1 / 2)
        mask3 = (~mask1) & (~mask2) & (t < 2 / 3)
        mask4 = (~mask1) & (~mask2) & (~mask3)
        result[mask1] = p[mask1] + (q[mask1] - p[mask1]) * 6.0 * t[mask1]
        result[mask2] = q[mask2]
        result[mask3] = p[mask3] + (q[mask3] - p[mask3]) * (2 / 3 - t[mask3]) * 6.0
        result[mask4] = p[mask4]
        return result

    chromatic = s > 0
    if np.any(chromatic):
        rgb[chromatic, 0] = hue_to_rgb(
            p[chromatic], q[chromatic], h[chromatic] + 1 / 3
        )
        rgb[chromatic, 1] = hue_to_rgb(p[chromatic], q[chromatic], h[chromatic])
        rgb[chromatic, 2] = hue_to_rgb(
            p[chromatic], q[chromatic], h[chromatic] - 1 / 3
        )

    achromatic = ~chromatic
    if np.any(achromatic):
        rgb[achromatic, 0] = l[achromatic]
        rgb[achromatic, 1] = l[achromatic]
        rgb[achromatic, 2] = l[achromatic]

    return rgb


def _srgb_to_hsl(rgb: NDArray) -> NDArray:
    r = rgb[..., 0]
    g = rgb[..., 1]
    b = rgb[..., 2]

    maxc = np.max(rgb, axis=-1)
    minc = np.min(rgb, axis=-1)
    l = (minc + maxc) / 2.0

    h = np.zeros_like(l, dtype=np.float64)
    s = np.zeros_like(l, dtype=np.float64)

    mask = maxc != minc
    if np.any(mask):
        d = (maxc - minc)[mask]
        lm = l[mask]

        s[mask] = np.where(
            lm > 0.5,
            d / (2.0 - maxc[mask] - minc[mask]),
            d / (maxc[mask] + minc[mask]),
        )

        rm = r[mask]
        gm = g[mask]
        bm = b[mask]
        maxm = maxc[mask]

        hr = (gm - bm) / d
        hg = (bm - rm) / d + 2.0
        hb = (rm - gm) / d + 4.0

        hm = np.empty_like(d, dtype=np.float64)
        is_r = maxm == rm
        is_g = (~is_r) & (maxm == gm)
        is_b = (~is_r) & (~is_g)

        hm[is_r] = hr[is_r]
        hm[is_g] = hg[is_g]
        hm[is_b] = hb[is_b]

        hm /= 6.0
        hm = np.mod(hm, 1.0)
        h[mask] = hm

    return np.stack([h, s, l], axis=-1)


def _srgb_to_hsv(rgb: NDArray) -> NDArray:
    rgb = np.clip(rgb, 0.0, 1.0).astype(np.float64)
    r = rgb[..., 0]
    g = rgb[..., 1]
    b = rgb[..., 2]

    maxc = np.max(rgb, axis=-1)
    minc = np.min(rgb, axis=-1)
    delta = maxc - minc

    v = maxc
    s = np.where(maxc <= 1e-10, 0.0, delta / np.maximum(maxc, 1e-10))

    h = np.zeros_like(maxc)
    mask = delta > 1e-6
    if np.any(mask):
        # Compute normalized color differences without pre-filtering
        rc = (maxc - r) / np.maximum(delta, 1e-10)
        gc = (maxc - g) / np.maximum(delta, 1e-10)
        bc = (maxc - b) / np.maximum(delta, 1e-10)

        rmask = (maxc == r) & mask
        gmask = (maxc == g) & mask
        bmask = (maxc == b) & mask

        h[rmask] = (bc - gc)[rmask]
        h[gmask] = (2.0 + rc - bc)[gmask]
        h[bmask] = (4.0 + gc - rc)[bmask]
        h = (h / 6.0) % 1.0

    hsv = np.stack([h, s, v], axis=-1)
    return hsv.astype(np.float32)


def _hsv_to_srgb(hsv: NDArray) -> NDArray:
    hsv = np.clip(hsv, 0.0, 1.0).astype(np.float64)
    h = hsv[..., 0]
    s = hsv[..., 1]
    v = hsv[..., 2]

    i = np.floor(h * 6.0).astype(np.int32)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)

    i_mod = np.mod(i, 6)
    shape = (*hsv.shape[:-1], 3)
    rgb = np.empty(shape, dtype=np.float64)

    mask0 = i_mod == 0
    mask1 = i_mod == 1
    mask2 = i_mod == 2
    mask3 = i_mod == 3
    mask4 = i_mod == 4
    mask5 = i_mod == 5

    rgb[mask0] = np.stack([v, t, p], axis=-1)[mask0]
    rgb[mask1] = np.stack([q, v, p], axis=-1)[mask1]
    rgb[mask2] = np.stack([p, v, t], axis=-1)[mask2]
    rgb[mask3] = np.stack([p, q, v], axis=-1)[mask3]
    rgb[mask4] = np.stack([t, p, v], axis=-1)[mask4]
    rgb[mask5] = np.stack([v, p, q], axis=-1)[mask5]

    achromatic = s <= 1e-6
    if np.any(achromatic):
        rgb[achromatic] = np.stack([v, v, v], axis=-1)[achromatic]

    return np.clip(rgb, 0.0, 1.0).astype(np.float32)
