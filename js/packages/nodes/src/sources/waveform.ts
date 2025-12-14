/**
 * WaveformNode - Generates configurable waveforms.
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

export type WaveShape = 'sine' | 'triangle' | 'sawtooth' | 'attack_decay' | 'square';

export interface IWaveformConfig {
  id: string;
  shape?: WaveShape;
  frequencyHz?: number;
  outputChannels?: number;
  attackRatio?: number;
  duty?: number;
  topic?: string;
}

/**
 * Attack-decay wave (fast rise, slow decay).
 */
function attackDecayWave(phase: Float32Array, attackRatio: number): Float32Array {
  const result = new Float32Array(phase.length);
  for (let i = 0; i < phase.length; i++) {
    const p = phase[i];
    if (p < attackRatio) {
      result[i] = p / attackRatio;
    } else {
      result[i] = 1.0 - (p - attackRatio) / (1.0 - attackRatio);
    }
  }
  return result;
}

function triangleWave(phase: Float32Array): Float32Array {
  const result = new Float32Array(phase.length);
  for (let i = 0; i < phase.length; i++) {
    const p = phase[i];
    result[i] = p < 0.5 ? p * 2.0 : 2.0 - p * 2.0;
  }
  return result;
}

function sawtoothWave(phase: Float32Array): Float32Array {
  return phase;
}

function squareWave(phase: Float32Array, duty: number): Float32Array {
  const result = new Float32Array(phase.length);
  for (let i = 0; i < phase.length; i++) {
    result[i] = phase[i] < duty ? 1.0 : 0.0;
  }
  return result;
}

function sineWave(phase: Float32Array): Float32Array {
  const result = new Float32Array(phase.length);
  for (let i = 0; i < phase.length; i++) {
    result[i] = (Math.sin(phase[i] * 2.0 * Math.PI) + 1.0) / 2.0;
  }
  return result;
}

@node('WaveformNode', 'Waveform')
export class WaveformNode extends BaseNode {
  readonly inputs = PortGroup.inputs({
    phase: new InputPortSpec({ accepts: 'matrix' }),
    speed: new InputPortSpec({ accepts: 'matrix' }),
  });

  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: 'matrix' }),
  });

  private readonly _channels: number;
  private readonly _shape: WaveShape;
  private readonly _frequencyHz: number;
  private readonly _attackRatio: number;
  private readonly _duty: number;
  private readonly _topic: string;

  constructor(config: IWaveformConfig) {
    super(config);
    this._channels = config.outputChannels ?? 512;
    this._shape = config.shape ?? 'sine';
    this._frequencyHz = config.frequencyHz ?? 1.0;
    this._attackRatio = config.attackRatio ?? 0.33;
    this._duty = config.duty ?? 0.5;
    this._topic = config.topic ?? `waveform.${this.id}`;
  }

  override async pull(tick: ITickContext): Promise<void> {
    const t = tick.t;
    const basePhase = (this._frequencyHz * t) % 1.0;

    // Read optional modulation inputs
    let phaseOffsets: Float32Array | null = null;
    let speedMultipliers: Float32Array | null = null;

    const phasePort = this.inputs.get('phase');
    const phaseFrame = phasePort ? (phasePort as unknown as { read: () => Frame | null }).read() : null;
    if (phaseFrame) {
      phaseOffsets = (phaseFrame.payload as MatrixPayload).flatten();
    }

    const speedPort = this.inputs.get('speed');
    const speedFrame = speedPort ? (speedPort as unknown as { read: () => Frame | null }).read() : null;
    if (speedFrame) {
      speedMultipliers = (speedFrame.payload as MatrixPayload).flatten();
    }

    // Compute phase for each channel
    const phase = new Float32Array(this._channels);
    for (let i = 0; i < this._channels; i++) {
      let p = basePhase;
      if (speedMultipliers && i < speedMultipliers.length) {
        p = (basePhase * speedMultipliers[i]) % 1.0;
      }
      if (phaseOffsets && i < phaseOffsets.length) {
        p = (p + phaseOffsets[i]) % 1.0;
      }
      phase[i] = p;
    }

    // Apply waveform shape
    const values = this._applyShape(phase);

    const payload = new MatrixPayload(values, 1);
    const frame = new Frame({
      topic: this._topic,
      timestamp: tick.wallTime,
      payload,
      metadata: this._metadata,
    });

    const outPort = this.outputs.get('out');
    if (outPort) (outPort as unknown as { write: (f: Frame) => void }).write(frame);
  }

  private _applyShape(phase: Float32Array): Float32Array {
    switch (this._shape) {
      case 'sine':
        return sineWave(phase);
      case 'triangle':
        return triangleWave(phase);
      case 'sawtooth':
        return sawtoothWave(phase);
      case 'attack_decay':
        return attackDecayWave(phase, this._attackRatio);
      case 'square':
        return squareWave(phase, this._duty);
      default:
        return sineWave(phase);
    }
  }
}
