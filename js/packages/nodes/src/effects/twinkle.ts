/**
 * TwinkleEffectNode - Applies TwinkleFOX-style modulation to color data.
 *
 * Each pixel gets a random phase offset and speed multiplier, creating
 * organic, non-synchronized twinkling.
 *
 * Modes:
 * - brightness: Multiply RGB by envelope → fade to black (classic twinkle)
 * - whiteness: Reduce saturation by envelope → fade to white (sparkle)
 */

import {
  BaseNode,
  Frame,
  MatrixPayload,
  PortGroup,
  InputPortSpec,
  OutputPortSpec,
  type ITickContext,
  node,
} from '@rasl/engine';

export type TwinkleMode = 'brightness' | 'whiteness';

export interface ITwinkleConfig {
  id: string;
  seed?: number;
  mode?: TwinkleMode;
  frequencyHz?: number;
  attackRatio?: number;
  minSpeed?: number;
  maxSpeed?: number;
  topic?: string;
}

function attackDecayWave(phase: Float32Array, attackRatio: number): Float32Array {
  const result = new Float32Array(phase.length);
  for (let i = 0; i < phase.length; i++) {
    const p = phase[i] % 1.0;
    if (p < attackRatio) {
      result[i] = p / attackRatio;
    } else {
      result[i] = 1.0 - (p - attackRatio) / (1.0 - attackRatio);
    }
  }
  return result;
}

// Simple seeded PRNG (mulberry32)
function seededRandom(seed: number): () => number {
  return function () {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

@node('TwinkleEffectNode', 'TwinkleEffect')
export class TwinkleEffectNode extends BaseNode {
  readonly inputs = PortGroup.inputs({
    in: new InputPortSpec({ accepts: ['matrix', 'color'] }),
  });

  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: 'color' }),
  });

  private readonly _seed: number;
  private readonly _mode: TwinkleMode;
  private readonly _frequencyHz: number;
  private readonly _attackRatio: number;
  private readonly _minSpeed: number;
  private readonly _maxSpeed: number;
  private readonly _topic: string;

  private _phaseOffsets: Float32Array | null = null;
  private _speedMultipliers: Float32Array | null = null;
  private _numPixels: number | null = null;

  constructor(config: ITwinkleConfig) {
    super(config);
    this._seed = config.seed ?? 42;
    this._mode = config.mode ?? 'brightness';
    this._frequencyHz = config.frequencyHz ?? 0.3;
    this._attackRatio = config.attackRatio ?? 0.33;
    this._minSpeed = config.minSpeed ?? 1.0;
    this._maxSpeed = config.maxSpeed ?? 3.0;
    this._topic = config.topic ?? `twinkle.${this.id}`;
  }

  private _initializeForSize(numPixels: number): void {
    if (this._numPixels === numPixels) return;

    this._numPixels = numPixels;

    // Generate phase offsets [0, 1)
    const rngPhase = seededRandom(this._seed);
    this._phaseOffsets = new Float32Array(numPixels);
    for (let i = 0; i < numPixels; i++) {
      this._phaseOffsets[i] = rngPhase();
    }

    // Generate speed multipliers [minSpeed, maxSpeed]
    const rngSpeed = seededRandom(this._seed + 1);
    this._speedMultipliers = new Float32Array(numPixels);
    for (let i = 0; i < numPixels; i++) {
      this._speedMultipliers[i] =
        rngSpeed() * (this._maxSpeed - this._minSpeed) + this._minSpeed;
    }
  }

  override async pull(tick: ITickContext): Promise<void> {
    const inPort = this.inputs.get('in');
    const frame = inPort
      ? (inPort as unknown as { read: () => Frame | null }).read()
      : null;
    if (!frame) return;

    const payload = frame.payload as MatrixPayload;
    const data = payload.flatten();
    const channels = payload.channels;

    // Determine number of pixels (assuming RGB = 3 channels per pixel)
    const numPixels = Math.floor(data.length / channels);
    if (numPixels <= 0) return;

    // Initialize per-pixel values if needed
    this._initializeForSize(numPixels);

    // Calculate current phase for each pixel
    const t = tick.t;
    const basePhase = t * this._frequencyHz;
    const pixelPhases = new Float32Array(numPixels);
    for (let i = 0; i < numPixels; i++) {
      pixelPhases[i] =
        (basePhase * this._speedMultipliers![i] + this._phaseOffsets![i]) % 1.0;
    }

    // Generate envelope [0, 1]
    const envelope = attackDecayWave(pixelPhases, this._attackRatio);

    // Apply effect based on mode
    const outData = new Float32Array(data.length);

    if (this._mode === 'brightness') {
      // Brightness mode: multiply RGB by envelope → fade to black
      for (let i = 0; i < numPixels; i++) {
        const e = envelope[i];
        for (let c = 0; c < channels; c++) {
          outData[i * channels + c] = data[i * channels + c] * e;
        }
      }
    } else {
      // Whiteness mode: reduce saturation → fade to white
      // For simplicity, we blend towards white (1,1,1)
      for (let i = 0; i < numPixels; i++) {
        const e = envelope[i];
        const blend = 1.0 - e; // 0 = original, 1 = white
        for (let c = 0; c < channels; c++) {
          const original = data[i * channels + c];
          outData[i * channels + c] = original + (1.0 - original) * blend;
        }
      }
    }

    const outPayload = new MatrixPayload(outData, channels);
    const outFrame = new Frame({
      topic: this._topic,
      timestamp: tick.wallTime,
      payload: outPayload,
      metadata: frame.metadata,
    });

    const outPort = this.outputs.get('out');
    if (outPort) {
      (outPort as unknown as { write: (f: Frame) => void }).write(outFrame);
    }
  }
}
