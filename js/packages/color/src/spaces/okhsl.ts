/**
 * OkHSL color space conversions.
 * Simplified implementation - full implementation would require toe/cusp calculations.
 */

import { oklabToOklch, oklchToOklab } from './oklch.js';

/**
 * Convert Oklab to OkHSL (simplified).
 */
export function oklabToOkhsl(lab: [number, number, number]): [number, number, number] {
  const [L, C, h] = oklabToOklch(lab);
  // Simplified: treat C as saturation proxy
  const s = C > 0 ? Math.min(C / 0.4, 1) : 0;
  return [h, s, L];
}

/**
 * Convert OkHSL to Oklab (simplified).
 */
export function okhslToOklab(hsl: [number, number, number]): [number, number, number] {
  const [h, s, l] = hsl;
  const C = s * 0.4;
  return oklchToOklab([l, C, h]);
}
