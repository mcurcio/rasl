/**
 * @rasl/color - Color conversion utilities
 */

export { type ColorModel, convert, normalizeModel } from "./convert.js";

// Direct conversion functions
export { hslToSrgb, srgbToHsl } from "./spaces/hsl.js";
export { okhslToOklab, oklabToOkhsl } from "./spaces/okhsl.js";
export { okhsvToOklab, oklabToOkhsv } from "./spaces/okhsv.js";
export { linearToOklab, oklabToLinear } from "./spaces/oklab.js";
export { oklabToOklch, oklchToOklab } from "./spaces/oklch.js";
export { linearToSrgb, srgbToLinear } from "./spaces/srgb.js";

// Color-aware nodes
export { type ILiteralConfig, LiteralNode } from "./nodes/sources/literal.js";
export { ColorNode, ColorPayload, type IColorConfig } from "./nodes/transforms/color.js";
export { ComposeNode, ComposeOutputType, type IComposeConfig } from "./nodes/transforms/compose.js";
export { ColorCorrectionNode, type IColorCorrectionConfig } from "./nodes/transforms/correction.js";
