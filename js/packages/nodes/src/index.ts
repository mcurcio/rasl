/**
 * @rasl/nodes - Built-in source, transform, and sink nodes
 */

// Sources
export { WaveformNode, type IWaveformConfig, type WaveShape } from './sources/waveform.js';
export { SeededRandomNode, type ISeededRandomConfig, type OutputType } from './sources/seeded-random.js';
export { LiteralNode, type ILiteralConfig } from './sources/literal.js';
export { SacnSourceNode, type ISacnSourceConfig } from './sources/sacn.js';

// Transforms
export { MathNode, type IMathConfig, type MathOperation } from './transforms/math.js';
export { ComposeNode, type IComposeConfig, ComposeOutputType } from './transforms/compose.js';
export { ColorNode, type IColorConfig, ColorPayload } from './transforms/color.js';
export { ColorCorrectionNode, type IColorCorrectionConfig } from './transforms/correction.js';

// Effects
export { TwinkleEffectNode, type ITwinkleConfig, type TwinkleMode } from './effects/twinkle.js';
export { CrossfadeNode, type ICrossfadeConfig } from './effects/crossfade.js';
export { CronNode, type ICronConfig } from './effects/cron.js';

// Sinks
export { ConsoleSink, type IConsoleSinkConfig } from './sinks/console.js';
export { DdpSinkNode, type IDdpSinkConfig } from './sinks/ddp.js';
export { SacnSinkNode, type ISacnSinkConfig } from './sinks/sacn.js';
