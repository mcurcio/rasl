"""Color conversion utilities wrapping colour-science.

All conversions route through XYZ as the hub space, which is what
colour-science uses internally. This ensures mathematically correct
transformations between any supported color models.

OKLCH is the recommended internal model for animation and mixing
due to its perceptual uniformity.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

import colour

# Suppress colour-science warnings about domain/range
colour.utilities.filter_warnings(colour_usage_warnings=False)

# Supported color models
MODELS: frozenset[str] = frozenset({"oklch", "oklab", "srgb", "rgb", "hsl", "okhsl", "okhsv", "linear"})

# Default internal model for mixing/animation
DEFAULT_MODEL: str = "oklch"


def convert(
    data: NDArray[np.float32],
    from_model: str,
    to_model: str,
) -> NDArray[np.float32]:
    """Convert color data between models.

    Uses direct conversion paths where available for performance,
    otherwise routes through XYZ as the hub space.
    Data shape: (N, 3) or flat (N*3,) - will be reshaped as needed.

    Args:
        data: Color data as float32 array, values in [0, 1].
        from_model: Source color model name.
        to_model: Target color model name.

    Returns:
        Converted color data with same shape as input.

    Raises:
        ValueError: If an unknown color model is specified.

    Example:
        >>> import numpy as np
        >>> hsl = np.array([[0.0, 1.0, 0.5]], dtype=np.float32)  # Red in HSL
        >>> rgb = convert(hsl, "hsl", "srgb")
    """
    # Normalize model names
    from_model = _normalize_model(from_model)
    to_model = _normalize_model(to_model)

    if from_model == to_model:
        return data

    original_shape = data.shape
    flat_data = data.reshape(-1)
    
    # Validate: color data must be RGB triplets (divisible by 3)
    if len(flat_data) % 3 != 0:
        raise ValueError(
            f"Color data must have length divisible by 3 (RGB triplets), "
            f"got {len(flat_data)} values. Use slicing to extract valid RGB data."
        )
    
    pixels = flat_data.reshape(-1, 3)

    # Fast paths for common conversions (bypass XYZ hub)
    result = _try_direct_convert(pixels, from_model, to_model)
    if result is not None:
        result = np.clip(result, 0.0, 1.0)
        return result.reshape(original_shape).astype(np.float32)

    # Fallback: route through XYZ hub space
    xyz = _to_xyz(pixels, from_model)
    result = _from_xyz(xyz, to_model)

    # Clip to valid range and restore shape
    result = np.clip(result, 0.0, 1.0)
    return result.reshape(original_shape).astype(np.float32)


def _try_direct_convert(
    data: NDArray,
    from_model: str,
    to_model: str,
) -> NDArray | None:
    """Try direct conversion without XYZ hub. Returns None if no direct path."""
    # OkHSL <-> sRGB (most common in this pipeline)
    if from_model == "okhsl" and to_model == "srgb":
        return _okhsl_to_srgb(data)
    if from_model == "srgb" and to_model == "okhsl":
        return _srgb_to_okhsl(data)
    
    # OkHSV <-> sRGB
    if from_model == "okhsv" and to_model == "srgb":
        return _okhsv_to_srgb(data)
    if from_model == "srgb" and to_model == "okhsv":
        return _srgb_to_okhsv(data)
    
    # Oklab <-> sRGB (direct, no XYZ needed)
    if from_model == "oklab" and to_model == "srgb":
        return _oklab_to_srgb_direct(data)
    if from_model == "srgb" and to_model == "oklab":
        return _srgb_to_oklab_direct(data)
    
    # HSL <-> sRGB
    if from_model == "hsl" and to_model == "srgb":
        return _hsl_to_srgb(data)
    if from_model == "srgb" and to_model == "hsl":
        return _srgb_to_hsl(data)
    
    # OKLCH <-> Oklab (simple coordinate transform)
    if from_model == "oklch" and to_model == "oklab":
        return _oklch_to_oklab(data)
    if from_model == "oklab" and to_model == "oklch":
        return _oklab_to_oklch(data)
    
    # OKLCH <-> sRGB via Oklab (faster than XYZ)
    if from_model == "oklch" and to_model == "srgb":
        oklab = _oklch_to_oklab(data)
        return _oklab_to_srgb_direct(oklab)
    if from_model == "srgb" and to_model == "oklch":
        oklab = _srgb_to_oklab_direct(data)
        return _oklab_to_oklch(oklab)
    
    # Linear RGB <-> sRGB (gamma only)
    if from_model == "linear" and to_model == "srgb":
        return _linear_to_srgb(data)
    if from_model == "srgb" and to_model == "linear":
        return _srgb_to_linear(data)
    
    return None


def _normalize_model(model: str) -> str:
    """Normalize model name aliases."""
    model = model.lower()
    if model == "rgb":
        return "srgb"
    if model == "linear_rgb" or model == "linearrgb":
        return "linear"
    if model not in MODELS:
        raise ValueError(f"Unknown color model: {model}. Supported: {sorted(MODELS)}")
    return model


def _to_xyz(data: NDArray, model: str) -> NDArray:
    """Convert any model to XYZ."""
    match model:
        case "srgb":
            return colour.sRGB_to_XYZ(data)
        case "linear":
            # Linear RGB to XYZ (no gamma, direct matrix)
            return colour.RGB_to_XYZ(data, "sRGB")
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
    """Convert XYZ to any model."""
    match model:
        case "srgb":
            return colour.XYZ_to_sRGB(xyz)
        case "linear":
            # XYZ to linear RGB (no gamma, direct matrix)
            return colour.XYZ_to_RGB(xyz, "sRGB")
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


def _oklab_to_oklch(oklab: NDArray) -> NDArray:
    """Oklab (L, a, b) → OKLCH (L, C, H).

    Hue is normalized to [0, 1] range (not degrees).
    """
    l = oklab[..., 0]
    a = oklab[..., 1]
    b = oklab[..., 2]

    c = np.sqrt(a**2 + b**2)
    h = np.arctan2(b, a) / (2 * np.pi)
    h = np.mod(h, 1.0)  # Ensure positive [0, 1]

    return np.stack([l, c, h], axis=-1)


def _oklch_to_oklab(oklch: NDArray) -> NDArray:
    """OKLCH (L, C, H) → Oklab (L, a, b).

    Hue expected in [0, 1] range (not degrees).
    """
    l = oklch[..., 0]
    c = oklch[..., 1]
    h = oklch[..., 2]

    h_rad = h * 2 * np.pi
    a = c * np.cos(h_rad)
    b = c * np.sin(h_rad)

    return np.stack([l, a, b], axis=-1)


def _hsl_to_srgb(hsl: NDArray) -> NDArray:
    """HSL → sRGB conversion.

    H, S, L all expected in [0, 1] range.
    Vectorized implementation for NumPy arrays.
    """
    h = hsl[..., 0]
    s = hsl[..., 1]
    l = hsl[..., 2]

    # Achromatic case
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
    """sRGB → HSL conversion.

    Returns H, S, L all in [0, 1] range.
    Vectorized implementation for NumPy arrays.
    """
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


# ─────────────────────────────────────────────────────────────────────────────
# sRGB <-> Linear RGB conversions (gamma only)
# ─────────────────────────────────────────────────────────────────────────────


def _srgb_to_linear(rgb: NDArray) -> NDArray:
    """Convert sRGB to linear RGB (remove gamma encoding).
    
    Uses the standard sRGB transfer function:
    - Linear portion for values <= 0.04045
    - Power curve (gamma ~2.4) for values > 0.04045
    
    Args:
        rgb: sRGB values in [0, 1] range, shape (..., 3)
        
    Returns:
        Linear RGB values in [0, 1] range
    """
    return np.where(
        rgb <= 0.04045,
        rgb / 12.92,
        np.power((rgb + 0.055) / 1.055, 2.4)
    ).astype(np.float32)


def _linear_to_srgb(linear: NDArray) -> NDArray:
    """Convert linear RGB to sRGB (apply gamma encoding).
    
    Uses the standard sRGB transfer function:
    - Linear portion for values <= 0.0031308
    - Power curve (gamma ~1/2.4) for values > 0.0031308
    
    Args:
        linear: Linear RGB values in [0, 1] range, shape (..., 3)
        
    Returns:
        sRGB values in [0, 1] range
    """
    return np.where(
        linear <= 0.0031308,
        12.92 * linear,
        1.055 * np.power(np.maximum(linear, 0), 1/2.4) - 0.055
    ).astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# OkHSL and OkHSV conversions
# Based on Björn Ottosson's reference implementation:
# https://bottosson.github.io/posts/colorpicker/
#
# This is a faithful port of Ottosson's algorithm with proper gamut mapping.
# ─────────────────────────────────────────────────────────────────────────────


def _srgb_to_oklab_direct(rgb: NDArray) -> NDArray:
    """Convert sRGB to Oklab directly (without going through XYZ).
    
    This is faster and more precise for OkHSL/OkHSV conversions.
    """
    # Linearize sRGB
    linear = np.where(
        rgb <= 0.04045,
        rgb / 12.92,
        np.power((rgb + 0.055) / 1.055, 2.4)
    )
    
    r = linear[..., 0]
    g = linear[..., 1]
    b = linear[..., 2]
    
    # sRGB to LMS
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    
    # Cube root
    l_ = np.cbrt(l)
    m_ = np.cbrt(m)
    s_ = np.cbrt(s)
    
    # LMS to Oklab
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b_out = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    
    return np.stack([L, a, b_out], axis=-1)


def _oklab_to_srgb_direct(oklab: NDArray) -> NDArray:
    """Convert Oklab to sRGB directly (without going through XYZ)."""
    L = oklab[..., 0]
    a = oklab[..., 1]
    b = oklab[..., 2]
    
    # Oklab to LMS
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    
    # Cube
    l = l_ ** 3
    m = m_ ** 3
    s = s_ ** 3
    
    # LMS to linear sRGB
    r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b_out = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    
    linear = np.stack([r, g, b_out], axis=-1)
    
    # Gamma encode
    rgb = np.where(
        linear <= 0.0031308,
        12.92 * linear,
        1.055 * np.power(np.maximum(linear, 0), 1/2.4) - 0.055
    )
    
    return np.clip(rgb, 0, 1)


def _oklab_to_linear_rgb(oklab: NDArray) -> NDArray:
    """Convert Oklab to linear RGB (no gamma, for gamut calculations)."""
    L = oklab[..., 0]
    a = oklab[..., 1]
    b = oklab[..., 2]
    
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    
    l = l_ ** 3
    m = m_ ** 3
    s = s_ ** 3
    
    r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b_out = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    
    return np.stack([r, g, b_out], axis=-1)


# Toe function constants (contrast curve for OkHSL/OkHSV)
_K1 = 0.206
_K2 = 0.03
_K3 = (1.0 + _K1) / (1.0 + _K2)


def _toe(x: float | NDArray) -> float | NDArray:
    """Toe function for perceptual lightness mapping."""
    x = np.asarray(x, dtype=np.float64)
    return 0.5 * (_K3 * x - _K1 + np.sqrt((_K3 * x - _K1) ** 2 + 4 * _K2 * _K3 * x))


def _toe_inv(x: float | NDArray) -> float | NDArray:
    """Inverse toe function."""
    x = np.asarray(x, dtype=np.float64)
    return (x * x + _K1 * x) / (_K3 * (x + _K2))


def _compute_max_saturation(a: NDArray, b: NDArray) -> NDArray:
    """Compute maximum saturation for given hue directions (vectorized).
    
    This finds where the line from white through the color intersects the sRGB gamut.
    Uses Halley's method for refinement.
    """
    # Conditions for which RGB component limits first
    cond_r = (-1.88170328 * a - 0.80936493 * b) > 1
    cond_g = (1.81444104 * a - 1.19445276 * b) > 1
    
    # Red coefficients
    k0_r, k1_r, k2_r, k3_r, k4_r = 1.19086277, 1.76576728, 0.59662641, 0.75515197, 0.56771245
    wl_r, wm_r, ws_r = 4.0767416621, -3.3077115913, 0.2309699292
    
    # Green coefficients
    k0_g, k1_g, k2_g, k3_g, k4_g = 0.73956515, -0.45954404, 0.08285427, 0.12541070, 0.14503204
    wl_g, wm_g, ws_g = -1.2684380046, 2.6097574011, -0.3413193965
    
    # Blue coefficients (default)
    k0_b, k1_b, k2_b, k3_b, k4_b = 1.35733652, -0.00915799, -1.15130210, -0.50559606, 0.00692167
    wl_b, wm_b, ws_b = -0.0041960863, -0.7034186147, 1.7076147010
    
    # Select coefficients based on conditions
    k0 = np.where(cond_r, k0_r, np.where(cond_g, k0_g, k0_b))
    k1 = np.where(cond_r, k1_r, np.where(cond_g, k1_g, k1_b))
    k2 = np.where(cond_r, k2_r, np.where(cond_g, k2_g, k2_b))
    k3 = np.where(cond_r, k3_r, np.where(cond_g, k3_g, k3_b))
    k4 = np.where(cond_r, k4_r, np.where(cond_g, k4_g, k4_b))
    wl = np.where(cond_r, wl_r, np.where(cond_g, wl_g, wl_b))
    wm = np.where(cond_r, wm_r, np.where(cond_g, wm_g, wm_b))
    ws = np.where(cond_r, ws_r, np.where(cond_g, ws_g, ws_b))
    
    sat = k0 + k1 * a + k2 * b + k3 * a * a + k4 * a * b
    
    # One Halley iteration refinement
    k_l = 0.3963377774 * a + 0.2158037573 * b
    k_m = -0.1055613458 * a - 0.0638541728 * b
    k_s = -0.0894841775 * a - 1.2914855480 * b
    
    l_ = 1 + sat * k_l
    m_ = 1 + sat * k_m
    s_ = 1 + sat * k_s
    
    l = l_ ** 3
    m = m_ ** 3
    s = s_ ** 3
    
    l_ds = 3 * k_l * l_ * l_
    m_ds = 3 * k_m * m_ * m_
    s_ds = 3 * k_s * s_ * s_
    
    l_ds2 = 6 * k_l * k_l * l_
    m_ds2 = 6 * k_m * k_m * m_
    s_ds2 = 6 * k_s * k_s * s_
    
    f = wl * l + wm * m + ws * s
    f1 = wl * l_ds + wm * m_ds + ws * s_ds
    f2 = wl * l_ds2 + wm * m_ds2 + ws * s_ds2
    
    sat = sat - f * f1 / (f1 * f1 - 0.5 * f * f2 + 1e-10)
    return sat


def _get_cusp(a: NDArray, b: NDArray) -> tuple[NDArray, NDArray]:
    """Find the cusp (L_cusp, C_cusp) for given hue directions (vectorized)."""
    s_cusp = _compute_max_saturation(a, b)
    
    # Build Oklab array for linear RGB conversion
    ones = np.ones_like(a)
    lab = np.stack([ones, s_cusp * a, s_cusp * b], axis=-1)
    rgb_lin = _oklab_to_linear_rgb(lab)
    
    # Find max RGB component
    max_rgb = np.maximum(np.maximum(rgb_lin[..., 0], rgb_lin[..., 1]), rgb_lin[..., 2])
    max_rgb = np.maximum(max_rgb, 1e-10)
    
    l_cusp = (1.0 / max_rgb) ** (1 / 3)
    c_cusp = l_cusp * s_cusp
    return l_cusp, c_cusp


def _st_mid(a: NDArray, b: NDArray) -> tuple[NDArray, NDArray]:
    """Compute mid saturation polynomial (vectorized)."""
    s = 0.11516993 + 1.0 / (
        7.44778970
        + 4.15901240 * b
        + a * (
            -2.19557347
            + 1.75198401 * b
            + a * (
                -2.13704948
                - 10.02301043 * b
                + a * (-4.24894561 + 5.38770819 * b + 4.69891013 * a)
            )
        )
    )
    t = 0.11239642 + 1.0 / (
        1.61320320
        - 0.68124379 * b
        + a * (
            0.40370612
            + 0.90148123 * b
            + a * (
                -0.27087943
                + 0.61223990 * b
                + a * (0.00299215 - 0.45399568 * b - 0.14661872 * a)
            )
        )
    )
    return s, t


def _get_cs(L: NDArray, a: NDArray, b: NDArray) -> tuple[NDArray, NDArray, NDArray]:
    """Get c0, c_mid, c_max for given L and normalized (a,b) direction (vectorized)."""
    l_cusp, c_cusp = _get_cusp(a, b)
    
    # S_max and T_max from cusp
    s_max = c_cusp / (l_cusp + 1e-10)
    t_max = c_cusp / (1 - l_cusp + 1e-10)
    
    # Maximum chroma for this L
    denom = np.minimum(L * s_max, (1 - L) * t_max)
    denom = np.maximum(denom, 1e-10)
    k = np.where((L > 0) & (L < 1), c_cusp / denom, 0.0)
    
    s_mid, t_mid = _st_mid(a, b)
    
    # Soft minimum between the L side and the (1-L) side
    c_a = L * s_mid
    c_b = (1 - L) * t_mid
    c_a4 = c_a ** 4 + 1e-10
    c_b4 = c_b ** 4 + 1e-10
    c_mid = 0.9 * k * np.sqrt(np.sqrt(1.0 / (1.0 / c_a4 + 1.0 / c_b4)))
    
    # Base chroma c0 (hue-independent-ish)
    c_a0 = L * 0.4
    c_b0 = (1 - L) * 0.8
    c_a0_sq = c_a0 * c_a0 + 1e-10
    c_b0_sq = c_b0 * c_b0 + 1e-10
    c0 = np.sqrt(1.0 / (1.0 / c_a0_sq + 1.0 / c_b0_sq))
    
    c_max = k * c_cusp
    return c0, c_mid, c_max


# Keep scalar versions for reference/testing
def _compute_max_saturation_scalar(a: float, b: float) -> float:
    """Compute maximum saturation for a given hue direction (scalar version)."""
    return float(_compute_max_saturation(np.array([a]), np.array([b]))[0])


def _get_cusp_scalar(a: float, b: float) -> tuple[float, float]:
    """Find the cusp (L_cusp, C_cusp) for a given hue direction (scalar)."""
    l_cusp, c_cusp = _get_cusp(np.array([a]), np.array([b]))
    return float(l_cusp[0]), float(c_cusp[0])


def _get_cs_scalar(L: float, a: float, b: float) -> tuple[float, float, float]:
    """Get c0, c_mid, c_max for given L and normalized (a,b) direction (scalar)."""
    c0, c_mid, c_max = _get_cs(np.array([L]), np.array([a]), np.array([b]))
    return float(c0[0]), float(c_mid[0]), float(c_max[0])


# ─────────────────────────────────────────────────────────────────────────────
# Scalar OkHSL <-> Oklab conversions
# ─────────────────────────────────────────────────────────────────────────────

def _okhsl_to_oklab_scalar(h: float, s: float, l: float) -> tuple[float, float, float]:
    """Convert single OkHSL to Oklab."""
    L = float(_toe_inv(l))
    if L <= 0.0 or L >= 1.0 or s <= 0.0:
        return L, 0.0, 0.0

    angle = 2.0 * np.pi * h
    a_ = float(np.cos(angle))
    b_ = float(np.sin(angle))

    c0, c_mid, c_max = _get_cs_scalar(L, a_, b_)

    mid = 0.8
    if s < mid:
        t = s / mid
        k0 = 0.0
        k1 = mid * c0
        k2 = 1.0 - k1 / (c_mid + 1e-10)
    else:
        t = (s - mid) / (1.0 - mid)
        k0 = c_mid
        k1 = (1.0 - mid) * c_mid * c_mid / (mid * mid * c0 + 1e-10)
        k2 = 1.0 - k1 / (c_max - c_mid + 1e-10)

    c = k0 + t * k1 / (1.0 - k2 * t + 1e-10)
    return L, c * a_, c * b_


def _oklab_to_okhsl_scalar(L: float, a: float, b: float) -> tuple[float, float, float]:
    """Convert single Oklab to OkHSL."""
    c = float(np.hypot(a, b))
    if c < 1e-10:
        # Grayscale
        return 0.0, 0.0, float(_toe(L))

    a_ = a / c
    b_ = b / c
    h = 0.5 + 0.5 * float(np.arctan2(-b_, -a_) / np.pi)

    c0, c_mid, c_max = _get_cs_scalar(L, float(a_), float(b_))

    mid = 0.8
    if c < c_mid:
        k1 = mid * c0
        k2 = 1.0 - k1 / (c_mid + 1e-10)
        t = c / (k1 + k2 * c + 1e-10)
        s = t * mid
    else:
        k0 = c_mid
        k1 = (1.0 - mid) * c_mid * c_mid / (mid * mid * c0 + 1e-10)
        k2 = 1.0 - k1 / (c_max - c_mid + 1e-10)
        t = (c - k0) / (k1 + k2 * (c - k0) + 1e-10)
        s = mid + (1.0 - mid) * t

    l = float(_toe(L))
    return float(h % 1.0), float(np.clip(s, 0, 1)), l


# ─────────────────────────────────────────────────────────────────────────────
# Scalar OkHSV <-> Oklab conversions
# ─────────────────────────────────────────────────────────────────────────────

def _okhsv_to_oklab_scalar(h: float, s: float, v: float) -> tuple[float, float, float]:
    """Convert single OkHSV to Oklab."""
    if v <= 0.0:
        return 0.0, 0.0, 0.0

    L_v = float(_toe_inv(v))
    angle = 2.0 * np.pi * h
    a_ = float(np.cos(angle))
    b_ = float(np.sin(angle))

    l_cusp, c_cusp = _get_cusp_scalar(a_, b_)
    s_max, t_max = _get_st_max(l_cusp, c_cusp)
    s_0 = 0.5
    k = 1.0 - s_0 / (s_max + 1e-10)

    l_v = 1.0 - s * s_0 / (s_0 + t_max - t_max * k * s + 1e-10)
    c_v = s * t_max * s_0 / (s_0 + t_max - t_max * k * s + 1e-10)

    L = v * l_v
    c = v * c_v

    L_vt = float(_toe_inv(l_v))
    c_vt = c_v * L_vt / (l_v + 1e-10)

    L_new = float(_toe_inv(L))
    c = c * L_new / (L + 1e-10)
    L = L_new

    lab_vt = np.array([[L_vt, a_ * c_vt, b_ * c_vt]], dtype=np.float64)
    rgb_vt = _oklab_to_linear_rgb(lab_vt)[0]
    scale = float((1.0 / (np.max(np.maximum(rgb_vt, 1e-10)))) ** (1.0 / 3.0))

    L *= scale
    c *= scale

    return L, c * a_, c * b_


def _oklab_to_okhsv_scalar(L: float, a: float, b: float) -> tuple[float, float, float]:
    """Convert single Oklab to OkHSV."""
    c = float(np.hypot(a, b))
    v = float(_toe(L))
    if c < 1e-10:
        return 0.0, 0.0, v

    a_ = a / c
    b_ = b / c
    h = 0.5 + 0.5 * float(np.arctan2(-b_, -a_) / np.pi)

    l_cusp, c_cusp = _get_cusp_scalar(float(a_), float(b_))
    s_max, t_max = _get_st_max(l_cusp, c_cusp)
    s_0 = 0.5
    k = 1.0 - s_0 / (s_max + 1e-10)

    # Invert the triangle logic
    t = t_max / (c + L * t_max + 1e-10)
    l_v = t * L
    c_v = t * c

    L_vt = float(_toe_inv(l_v))
    c_vt = c_v * L_vt / (l_v + 1e-10)

    lab_vt = np.array([[L_vt, a_ * c_vt, b_ * c_vt]], dtype=np.float64)
    rgb_vt = _oklab_to_linear_rgb(lab_vt)[0]
    scale = float((1.0 / (np.max(np.maximum(rgb_vt, 1e-10)))) ** (1.0 / 3.0))

    L_scaled = L / scale
    c_scaled = c / scale

    c_scaled *= _toe(L_scaled) / (L_scaled + 1e-10)
    L_scaled = _toe(L_scaled)

    v = float(L_scaled / (l_v + 1e-10))
    s = float((s_0 + t_max) * c_v / (t_max * s_0 + t_max * k * c_v + 1e-10))
    return float(h % 1.0), float(np.clip(s, 0, 1)), float(np.clip(v, 0, 1))


# ─────────────────────────────────────────────────────────────────────────────
# Vectorized OkHSL <-> sRGB conversions
# ─────────────────────────────────────────────────────────────────────────────

def _srgb_to_okhsl(rgb: NDArray) -> NDArray:
    """Convert sRGB to OkHSL (fully vectorized).
    
    OkHSL is a perceptually uniform HSL-like space based on Oklab.
    H, S, L all in [0, 1] range.
    """
    oklab = _srgb_to_oklab_direct(rgb)
    L = oklab[..., 0]
    a = oklab[..., 1]
    b = oklab[..., 2]
    
    # Compute chroma and hue
    c = np.sqrt(a**2 + b**2)
    
    # Handle grayscale (c ≈ 0)
    is_gray = c < 1e-10
    
    # Normalize a, b to unit vector (safe division)
    c_safe = np.where(is_gray, 1.0, c)
    a_ = a / c_safe
    b_ = b / c_safe
    
    # Hue from atan2
    h = 0.5 + 0.5 * np.arctan2(-b_, -a_) / np.pi
    h = np.mod(h, 1.0)
    
    # Get c0, c_mid, c_max for saturation calculation
    c0, c_mid, c_max = _get_cs(L, a_, b_)
    
    # Compute saturation using piecewise function
    mid = 0.8
    
    # For c < c_mid
    k1_lo = mid * c0
    k2_lo = 1.0 - k1_lo / (c_mid + 1e-10)
    t_lo = c / (k1_lo + k2_lo * c + 1e-10)
    s_lo = t_lo * mid
    
    # For c >= c_mid
    k0_hi = c_mid
    k1_hi = (1.0 - mid) * c_mid * c_mid / (mid * mid * c0 + 1e-10)
    k2_hi = 1.0 - k1_hi / (c_max - c_mid + 1e-10)
    t_hi = (c - k0_hi) / (k1_hi + k2_hi * (c - k0_hi) + 1e-10)
    s_hi = mid + (1.0 - mid) * t_hi
    
    s = np.where(c < c_mid, s_lo, s_hi)
    s = np.clip(s, 0, 1)
    
    # Grayscale has s=0
    s = np.where(is_gray, 0.0, s)
    h = np.where(is_gray, 0.0, h)
    
    # Lightness uses toe function
    l = _toe(L)
    
    return np.stack([h, s, l], axis=-1).astype(np.float32)


def _okhsl_to_srgb(hsl: NDArray) -> NDArray:
    """Convert OkHSL to sRGB (fully vectorized).
    
    H, S, L expected in [0, 1] range.
    """
    hsl = np.asarray(hsl, dtype=np.float64)
    h = hsl[..., 0]
    s = hsl[..., 1]
    l = hsl[..., 2]
    
    # Inverse toe for lightness
    L = _toe_inv(l)
    
    # Handle edge cases
    is_black = L <= 0.0
    is_white = L >= 1.0
    is_gray = s <= 0.0
    is_achromatic = is_black | is_white | is_gray
    
    # Hue to unit vector
    angle = 2.0 * np.pi * h
    a_ = np.cos(angle)
    b_ = np.sin(angle)
    
    # Get c0, c_mid, c_max
    c0, c_mid, c_max = _get_cs(L, a_, b_)
    
    # Compute chroma from saturation using piecewise function
    mid = 0.8
    
    # For s < mid
    t_lo = s / mid
    k0_lo = 0.0
    k1_lo = mid * c0
    k2_lo = 1.0 - k1_lo / (c_mid + 1e-10)
    c_lo = k0_lo + t_lo * k1_lo / (1.0 - k2_lo * t_lo + 1e-10)
    
    # For s >= mid
    t_hi = (s - mid) / (1.0 - mid + 1e-10)
    k0_hi = c_mid
    k1_hi = (1.0 - mid) * c_mid * c_mid / (mid * mid * c0 + 1e-10)
    k2_hi = 1.0 - k1_hi / (c_max - c_mid + 1e-10)
    c_hi = k0_hi + t_hi * k1_hi / (1.0 - k2_hi * t_hi + 1e-10)
    
    c = np.where(s < mid, c_lo, c_hi)
    
    # Achromatic colors have c=0
    c = np.where(is_achromatic, 0.0, c)
    
    # Reconstruct Oklab
    a = c * a_
    b = c * b_
    
    oklab = np.stack([L, a, b], axis=-1)
    return _oklab_to_srgb_direct(oklab).astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# Vectorized OkHSV <-> sRGB conversions
# ─────────────────────────────────────────────────────────────────────────────

def _srgb_to_okhsv(rgb: NDArray) -> NDArray:
    """Convert sRGB to OkHSV (fully vectorized).
    
    OkHSV is a perceptually uniform HSV-like space based on Oklab.
    H, S, V all in [0, 1] range.
    """
    oklab = _srgb_to_oklab_direct(rgb)
    L = oklab[..., 0]
    a = oklab[..., 1]
    b = oklab[..., 2]
    
    c = np.sqrt(a**2 + b**2)
    
    # Handle grayscale
    is_gray = c < 1e-10
    
    c_safe = np.where(is_gray, 1.0, c)
    a_ = a / c_safe
    b_ = b / c_safe
    
    # Hue
    h = 0.5 + 0.5 * np.arctan2(-b_, -a_) / np.pi
    h = np.mod(h, 1.0)
    
    # Get cusp
    l_cusp, c_cusp = _get_cusp(a_, b_)
    s_max = c_cusp / (l_cusp + 1e-10)
    t_max = c_cusp / (1 - l_cusp + 1e-10)
    s_0 = 0.5
    k = 1.0 - s_0 / (s_max + 1e-10)
    
    # Invert the triangle logic
    t = t_max / (c + L * t_max + 1e-10)
    l_v = t * L
    c_v = t * c
    
    L_vt = _toe_inv(l_v)
    c_vt = c_v * L_vt / (l_v + 1e-10)
    
    # Build lab for scale calculation
    lab_vt = np.stack([L_vt, a_ * c_vt, b_ * c_vt], axis=-1)
    rgb_vt = _oklab_to_linear_rgb(lab_vt)
    max_rgb = np.maximum(np.maximum(rgb_vt[..., 0], rgb_vt[..., 1]), rgb_vt[..., 2])
    scale = (1.0 / np.maximum(max_rgb, 1e-10)) ** (1.0 / 3.0)
    
    L_scaled = L / scale
    c_scaled = c / scale
    
    c_scaled = c_scaled * _toe(L_scaled) / (L_scaled + 1e-10)
    L_scaled = _toe(L_scaled)
    
    v = L_scaled / (l_v + 1e-10)
    s = (s_0 + t_max) * c_v / (t_max * s_0 + t_max * k * c_v + 1e-10)
    
    # Grayscale
    h = np.where(is_gray, 0.0, h)
    s = np.where(is_gray, 0.0, s)
    v = np.where(is_gray, _toe(L), v)
    
    s = np.clip(s, 0, 1)
    v = np.clip(v, 0, 1)
    
    return np.stack([h, s, v], axis=-1).astype(np.float32)


def _okhsv_to_srgb(hsv: NDArray) -> NDArray:
    """Convert OkHSV to sRGB (fully vectorized).
    
    H, S, V expected in [0, 1] range.
    """
    hsv = np.asarray(hsv, dtype=np.float64)
    h = hsv[..., 0]
    s = hsv[..., 1]
    v = hsv[..., 2]
    
    # Handle v=0 (black)
    is_black = v <= 0.0
    
    L_v = _toe_inv(v)
    angle = 2.0 * np.pi * h
    a_ = np.cos(angle)
    b_ = np.sin(angle)
    
    # Get cusp
    l_cusp, c_cusp = _get_cusp(a_, b_)
    s_max = c_cusp / (l_cusp + 1e-10)
    t_max = c_cusp / (1 - l_cusp + 1e-10)
    s_0 = 0.5
    k = 1.0 - s_0 / (s_max + 1e-10)
    
    l_v = 1.0 - s * s_0 / (s_0 + t_max - t_max * k * s + 1e-10)
    c_v = s * t_max * s_0 / (s_0 + t_max - t_max * k * s + 1e-10)
    
    L = v * l_v
    c = v * c_v
    
    L_vt = _toe_inv(l_v)
    c_vt = c_v * L_vt / (l_v + 1e-10)
    
    L_new = _toe_inv(L)
    c = c * L_new / (L + 1e-10)
    L = L_new
    
    # Build lab for scale calculation
    lab_vt = np.stack([L_vt, a_ * c_vt, b_ * c_vt], axis=-1)
    rgb_vt = _oklab_to_linear_rgb(lab_vt)
    max_rgb = np.maximum(np.maximum(rgb_vt[..., 0], rgb_vt[..., 1]), rgb_vt[..., 2])
    scale = (1.0 / np.maximum(max_rgb, 1e-10)) ** (1.0 / 3.0)
    
    L = L * scale
    c = c * scale
    
    # Black case
    L = np.where(is_black, 0.0, L)
    c = np.where(is_black, 0.0, c)
    
    # Reconstruct Oklab
    a = c * a_
    b = c * b_
    
    oklab = np.stack([L, a, b], axis=-1)
    return _oklab_to_srgb_direct(oklab).astype(np.float32)
