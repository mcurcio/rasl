/**
 * Color conversion utilities.
 */
import { srgbToLinear, linearToSrgb } from './spaces/srgb.js';
import { hslToSrgb, srgbToHsl } from './spaces/hsl.js';
import { linearToOklab, oklabToLinear } from './spaces/oklab.js';
import { oklabToOklch, oklchToOklab } from './spaces/oklch.js';
import { oklabToOkhsl, okhslToOklab } from './spaces/okhsl.js';
import { oklabToOkhsv, okhsvToOklab } from './spaces/okhsv.js';
/**
 * Supported color models.
 */
export const ColorModel = {
    Srgb: 'srgb',
    Linear: 'linear',
    Hsl: 'hsl',
    Oklab: 'oklab',
    Oklch: 'oklch',
    Okhsl: 'okhsl',
    Okhsv: 'okhsv',
};
/**
 * Normalize a color model string to a canonical form.
 */
export function normalizeModel(model) {
    const lower = model.toLowerCase();
    switch (lower) {
        case 'srgb':
        case 'rgb':
            return ColorModel.Srgb;
        case 'linear':
        case 'linear-rgb':
            return ColorModel.Linear;
        case 'hsl':
            return ColorModel.Hsl;
        case 'oklab':
        case 'lab':
            return ColorModel.Oklab;
        case 'oklch':
        case 'lch':
            return ColorModel.Oklch;
        case 'okhsl':
            return ColorModel.Okhsl;
        case 'okhsv':
            return ColorModel.Okhsv;
        default:
            return ColorModel.Srgb;
    }
}
/**
 * Convert a color from one model to another.
 * All colors are represented as [c0, c1, c2] tuples.
 */
export function convert(color, from, to) {
    if (from === to)
        return color;
    // Convert to Oklab as intermediate
    let oklab;
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
//# sourceMappingURL=convert.js.map