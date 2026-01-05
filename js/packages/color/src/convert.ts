/**
 * Color conversion utilities.
 */

import { hslToSrgb, srgbToHsl } from "./spaces/hsl.js";
import { okhslToOklab,oklabToOkhsl } from "./spaces/okhsl.js";
import { okhsvToOklab,oklabToOkhsv } from "./spaces/okhsv.js";
import { linearToOklab, oklabToLinear } from "./spaces/oklab.js";
import { oklabToOklch, oklchToOklab } from "./spaces/oklch.js";
import { linearToSrgb,srgbToLinear } from "./spaces/srgb.js";

/**
 * Supported color models.
 */
export const ColorModel = {
  Srgb: "srgb",
  Linear: "linear",
  Hsl: "hsl",
  Oklab: "oklab",
  Oklch: "oklch",
  Okhsl: "okhsl",
  Okhsv: "okhsv",
} as const;
export type ColorModel = (typeof ColorModel)[keyof typeof ColorModel];

/**
 * Normalize a color model string to a canonical form.
 */
export function normalizeModel(model: string): ColorModel {
  const lower = model.toLowerCase();
  switch (lower) {
    case "srgb":
    case "rgb":
      return ColorModel.Srgb;
    case "linear":
    case "linear-rgb":
      return ColorModel.Linear;
    case "hsl":
      return ColorModel.Hsl;
    case "oklab":
    case "lab":
      return ColorModel.Oklab;
    case "oklch":
    case "lch":
      return ColorModel.Oklch;
    case "okhsl":
      return ColorModel.Okhsl;
    case "okhsv":
      return ColorModel.Okhsv;
    default:
      return ColorModel.Srgb;
  }
}

/**
 * Convert a color from one model to another.
 * All colors are represented as [c0, c1, c2] tuples.
 */
export function convert(color: [number, number, number], from: ColorModel, to: ColorModel): [number, number, number] {
  if (from === to) return color;

  // Convert to Oklab as intermediate
  let oklab: [number, number, number];

  switch (from) {
    case ColorModel.Srgb:
      oklab = linearToOklab(srgbToLinear(color));
      break;
    case ColorModel.Linear:
      oklab = linearToOklab(color);
      break;
    case ColorModel.Hsl:
      oklab = linearToOklab(srgbToLinear(hslToSrgb(color)));
      break;
    case ColorModel.Oklab:
      oklab = color;
      break;
    case ColorModel.Oklch:
      oklab = oklchToOklab(color);
      break;
    case ColorModel.Okhsl:
      oklab = okhslToOklab(color);
      break;
    case ColorModel.Okhsv:
      oklab = okhsvToOklab(color);
      break;
    default:
      oklab = color;
  }

  // Convert from Oklab to target
  switch (to) {
    case ColorModel.Srgb:
      return linearToSrgb(oklabToLinear(oklab));
    case ColorModel.Linear:
      return oklabToLinear(oklab);
    case ColorModel.Hsl:
      return srgbToHsl(linearToSrgb(oklabToLinear(oklab)));
    case ColorModel.Oklab:
      return oklab;
    case ColorModel.Oklch:
      return oklabToOklch(oklab);
    case ColorModel.Okhsl:
      return oklabToOkhsl(oklab);
    case ColorModel.Okhsv:
      return oklabToOkhsv(oklab);
    default:
      return oklab;
  }
}
