/**
 * @rasl/color - Color conversion utilities
 */

export { convert, normalizeModel, type ColorModel } from './convert.js';

// Direct conversion functions
export {
  srgbToLinear,
  linearToSrgb,
} from './spaces/srgb.js';

export {
  hslToSrgb,
  srgbToHsl,
} from './spaces/hsl.js';

export {
  linearToOklab,
  oklabToLinear,
} from './spaces/oklab.js';

export {
  oklabToOklch,
  oklchToOklab,
} from './spaces/oklch.js';

export {
  oklabToOkhsl,
  okhslToOklab,
} from './spaces/okhsl.js';

export {
  oklabToOkhsv,
  okhsvToOklab,
} from './spaces/okhsv.js';

// Color-aware nodes
export {
  ColorNode,
  type IColorConfig,
  ColorPayload,
} from './nodes/transforms/color.js';
export {
  ComposeNode,
  type IComposeConfig,
  ComposeOutputType,
} from './nodes/transforms/compose.js';
export {
  ColorCorrectionNode,
  type IColorCorrectionConfig,
} from './nodes/transforms/correction.js';
export {
  LiteralNode,
  type ILiteralConfig,
} from './nodes/sources/literal.js';
