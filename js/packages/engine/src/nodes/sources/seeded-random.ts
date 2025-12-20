/**
 * SeededRandomNode - Deterministic per-channel random values.
 */

import {
  BaseNode,
  Frame,
  type ITickContext,
  MatrixPayload,
  OutputPortSpec,
  PortGroup,
  node,
} from '../../runtime/index.js';

export type OutputType = 'phase' | 'speed' | 'uniform' | 'binary';

export interface ISeededRandomConfig {
  id: string;
  seed?: number;
  outputChannels?: number;
  outputType?: OutputType;
  minSpeed?: number;
  maxSpeed?: number;
  density?: number;
}

/**
 * Simple seeded PRNG (mulberry32).
 */
function mulberry32(seed: number): () => number {
  return function () {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

@node('SeededRandomNode', 'SeededRandom')
export class SeededRandomNode extends BaseNode {
  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: 'matrix' }),
  });

  private readonly _seed: number;
  private readonly _channels: number;
  private readonly _outputType: OutputType;
  private readonly _minSpeed: number;
  private readonly _maxSpeed: number;
  private readonly _density: number;
  private readonly _topic: string;

  constructor(config: ISeededRandomConfig) {
    super(config);
    this._seed = config.seed ?? 12345;
    this._channels = config.outputChannels ?? 512;
    this._outputType = config.outputType ?? 'uniform';
    this._minSpeed = config.minSpeed ?? 1.0;
    this._maxSpeed = config.maxSpeed ?? 3.0;
    this._density = config.density ?? 0.5;
    this._topic = `random.${this.id}`;
  }

  override async pull(tick: ITickContext): Promise<void> {
    // Regenerate same values each frame (deterministic)
    const rng = mulberry32(this._seed);
    const values = new Float32Array(this._channels);

    for (let i = 0; i < this._channels; i++) {
      const r = rng();

      switch (this._outputType) {
        case 'phase':
          values[i] = r;
          break;
        case 'speed':
          values[i] = this._minSpeed + r * (this._maxSpeed - this._minSpeed);
          break;
        case 'uniform':
          values[i] = r;
          break;
        case 'binary':
          values[i] = r < this._density ? 1.0 : 0.0;
          break;
      }
    }

    const payload = new MatrixPayload(values, 1);
    const frame = new Frame({
      topic: this._topic,
      timestamp: tick.wallTime,
      payload,
      metadata: this._metadata,
    });

    this.outputs.get('out')?.write(frame);
  }
}
