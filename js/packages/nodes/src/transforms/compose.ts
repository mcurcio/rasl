/**
 * ComposeNode - Combines multiple input ports into interleaved output.
 *
 * Useful for constructing multi-component data like HSL color from
 * separate H, S, L sources.
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

/**
 * Output type for compose node.
 */
export const ComposeOutputType = {
  Array: 'array',
  Rgb: 'rgb',
  Hsl: 'hsl',
  Oklch: 'oklch',
  Oklab: 'oklab',
  Okhsl: 'okhsl',
  Okhsv: 'okhsv',
} as const;
export type ComposeOutputType = (typeof ComposeOutputType)[keyof typeof ComposeOutputType];

export interface IComposeConfig {
  id: string;
  ports: string[];
  fill?: Record<string, number>;
  outputType?: ComposeOutputType;
  outputChannels?: number;
  topic?: string;
}

@node('ComposeNode', 'Compose')
export class ComposeNode extends BaseNode {
  readonly inputs: PortGroup;
  readonly outputs: PortGroup;

  private readonly _portNames: string[];
  private readonly _fills: Record<string, number>;
  private readonly _numPorts: number;
  private readonly _outputType: ComposeOutputType;
  private readonly _topic: string;
  private _resolvedLength: number | null;

  constructor(config: IComposeConfig) {
    super(config);
    this._portNames = config.ports;
    this._fills = config.fill ?? {};
    this._numPorts = this._portNames.length;
    this._outputType = config.outputType ?? ComposeOutputType.Array;
    this._topic = config.topic ?? `compose.${this.id}`;
    this._resolvedLength = config.outputChannels ?? null;

    // Create dynamic input ports based on config
    const inputSpecs: Record<string, InputPortSpec> = {};
    for (const name of this._portNames) {
      inputSpecs[name] = new InputPortSpec({ accepts: 'matrix' });
    }
    this.inputs = PortGroup.inputs(inputSpecs);

    this.outputs = PortGroup.outputs({
      out: new OutputPortSpec({ produces: this._outputType === 'array' ? 'matrix' : 'color' }),
    });
  }

  override async pull(tick: ITickContext): Promise<void> {
    const buffers: Map<string, Float32Array | null> = new Map();
    let count = this._resolvedLength;

    // Read all input ports
    for (const portName of this._portNames) {
      const port = this.inputs.get(portName);
      if (!port) {
        buffers.set(portName, null);
        continue;
      }

      const frame = (port as unknown as { read: () => Frame | null }).read();
      if (frame) {
        const data = (frame.payload as MatrixPayload).flatten();
        buffers.set(portName, data);
        if (count === null) {
          count = data.length;
        }
      } else {
        buffers.set(portName, null);
      }
    }

    if (count === null) {
      return;
    }

    this._resolvedLength = count;

    // Compose the matrix
    const out = this._composeMatrix(count, buffers);
    const payload = new MatrixPayload(out, this._numPorts);

    const frame = new Frame({
      topic: this._topic,
      timestamp: tick.wallTime,
      payload,
      metadata: this._metadata,
    });

    const outPort = this.outputs.get('out');
    if (outPort) {
      (outPort as unknown as { write: (f: Frame) => void }).write(frame);
    }
  }

  private _composeMatrix(count: number, buffers: Map<string, Float32Array | null>): Float32Array {
    const out = new Float32Array(count * this._numPorts);

    for (let i = 0; i < this._numPorts; i++) {
      const name = this._portNames[i];
      const fillValue = this._fills[name];

      if (fillValue !== undefined) {
        // Fill with constant value
        for (let j = 0; j < count; j++) {
          out[j * this._numPorts + i] = fillValue;
        }
        continue;
      }

      const buf = buffers.get(name);
      if (!buf) {
        continue;
      }

      const copyLen = Math.min(buf.length, count);
      for (let j = 0; j < copyLen; j++) {
        out[j * this._numPorts + i] = buf[j];
      }
    }

    return out;
  }
}
