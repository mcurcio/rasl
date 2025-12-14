/**
 * sRGB color space conversions.
 */

/**
 * Convert sRGB to linear RGB.
 */
export function srgbToLinear(srgb: [number, number, number]): [number, number, number] {
  return srgb.map((c) => {
    if (c <= 0.04045) {
      return c / 12.92;
    }
    return Math.pow((c + 0.055) / 1.055, 2.4);
  }) as [number, number, number];
}

/**
 * Convert linear RGB to sRGB.
 */
export function linearToSrgb(linear: [number, number, number]): [number, number, number] {
  return linear.map((c) => {
    if (c <= 0.0031308) {
      return c * 12.92;
    }
    return 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
  }) as [number, number, number];
}
