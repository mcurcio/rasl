/**
 * OkHSV color space conversions.
 * Simplified implementation - full implementation would require toe/cusp calculations.
 */

import { oklabToOklch, oklchToOklab } from "./oklch.js";

/**
 * Convert Oklab to OkHSV (simplified).
 */
export function oklabToOkhsv(lab: [number, number, number]): [number, number, number] {
  const [L, C, h] = oklabToOklch(lab);
  // Simplified: treat C as saturation proxy, L as value
  const s = C > 0 ? Math.min(C / 0.4, 1) : 0;
  return [h, s, L];
}

/**
 * Convert OkHSV to Oklab (simplified).
 */
export function okhsvToOklab(hsv: [number, number, number]): [number, number, number] {
  const [h, s, v] = hsv;
  const C = s * 0.4;
  return oklchToOklab([v, C, h]);
}
