/**
 * Oklch color space conversions.
 */

/**
 * Convert Oklab to Oklch.
 */
export function oklabToOklch(lab: [number, number, number]): [number, number, number] {
  const [L, a, b] = lab;
  const C = Math.sqrt(a * a + b * b);
  let h = Math.atan2(b, a) / (2 * Math.PI);
  if (h < 0) h += 1;
  return [L, C, h];
}

/**
 * Convert Oklch to Oklab.
 */
export function oklchToOklab(lch: [number, number, number]): [number, number, number] {
  const [L, C, h] = lch;
  const angle = h * 2 * Math.PI;
  return [L, C * Math.cos(angle), C * Math.sin(angle)];
}
