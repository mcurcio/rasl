/**
 * Color conversion utilities.
 */
/**
 * Supported color models.
 */
export declare const ColorModel: {
    readonly Srgb: "srgb";
    readonly Linear: "linear";
    readonly Hsl: "hsl";
    readonly Oklab: "oklab";
    readonly Oklch: "oklch";
    readonly Okhsl: "okhsl";
    readonly Okhsv: "okhsv";
};
export type ColorModel = (typeof ColorModel)[keyof typeof ColorModel];
/**
 * Normalize a color model string to a canonical form.
 */
export declare function normalizeModel(model: string): ColorModel;
/**
 * Convert a color from one model to another.
 * All colors are represented as [c0, c1, c2] tuples.
 */
export declare function convert(color: [number, number, number], from: ColorModel, to: ColorModel): [number, number, number];
//# sourceMappingURL=convert.d.ts.map