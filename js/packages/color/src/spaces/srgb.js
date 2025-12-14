/**
 * sRGB color space conversions.
 */
/**
 * Convert sRGB to linear RGB.
 */
export function srgbToLinear(srgb) {
    return srgb.map((c) => {
        if (c <= 0.04045) {
            return c / 12.92;
        }
        return Math.pow((c + 0.055) / 1.055, 2.4);
    });
}
/**
 * Convert linear RGB to sRGB.
 */
export function linearToSrgb(linear) {
    return linear.map((c) => {
        if (c <= 0.0031308) {
            return c * 12.92;
        }
        return 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
    });
}
//# sourceMappingURL=srgb.js.map