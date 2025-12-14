/**
 * MathNode - Element-wise math operations.
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

export type MathOperation = 'add' | 'subtract' | 'multiply' | 'divide' | 'min' | 'max' | 'lerp' | 'screen';

export interface IMathConfig {
  id: string;
  operation: MathOperation;
  constantA?: number;
  constantB?: number;
  mix?: number;
  clamp?: boolean;
}

@node('MathNode', 'Math')
export class MathNode extends BaseNode {
  readonly inputs = PortGroup.inputs({
    a: new InputPortSpec({ accepts: 'matrix' }),
    b: new InputPortSpec({ accepts: 'matrix' }),
  });

  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: 'matrix' }),
  });

  private readonly _operation: MathOperation;
  private readonly _constantA: number;
  private readonly _constantB: number;
  private readonly _mix: number;
  private readonly _clamp: boolean;
  private readonly _topic: string;

  constructor(config: IMathConfig) {
    super(config);
    this._operation = config.operation;
    this._constantA = config.constantA ?? 0;
    this._constantB = config.constantB ?? 0;
    this._mix = config.mix ?? 0.5;
    this._clamp = config.clamp ?? true;
    this._topic = `math.${this.id}`;
  }

  override async pull(tick: ITickContext): Promise<void> {
    const portA = this.inputs.get('a');
    const portB = this.inputs.get('b');
    const frameA = portA ? (portA as unknown as { read: () => Frame | null }).read() : null;
    const frameB = portB ? (portB as unknown as { read: () => Frame | null }).read() : null;

    // Get data arrays
    let dataA: Float32Array;
    let dataB: Float32Array;
    let count: number;

    if (frameA) {
      const payloadA = frameA.payload as MatrixPayload;
      dataA = payloadA.flatten();
      count = payloadA.count;
    } else {
      count = 512;
      dataA = new Float32Array(count);
      dataA.fill(this._constantA);
    }

    if (frameB) {
      const payloadB = frameB.payload as MatrixPayload;
      dataB = payloadB.flatten();
      count = Math.max(count, payloadB.count);
    } else {
      dataB = new Float32Array(count);
      dataB.fill(this._constantB);
    }

    // Perform operation
    const result = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const a = i < dataA.length ? dataA[i] : this._constantA;
      const b = i < dataB.length ? dataB[i] : this._constantB;

      let value: number;
      switch (this._operation) {
        case 'add':
          value = a + b;
          break;
        case 'subtract':
          value = a - b;
          break;
        case 'multiply':
          value = a * b;
          break;
        case 'divide':
          value = b !== 0 ? a / b : 0;
          break;
        case 'min':
          value = Math.min(a, b);
          break;
        case 'max':
          value = Math.max(a, b);
          break;
        case 'lerp':
          value = a + (b - a) * this._mix;
          break;
        case 'screen':
          value = 1 - (1 - a) * (1 - b);
          break;
        default:
          value = a;
      }

      if (this._clamp) {
        value = Math.max(0, Math.min(1, value));
      }

      result[i] = value;
    }

    const payload = new MatrixPayload(result, 1);
    const frame = new Frame({
      topic: this._topic,
      timestamp: tick.wallTime,
      payload,
      metadata: this._metadata,
    });

    const outPort = this.outputs.get('out');
    if (outPort) (outPort as unknown as { write: (f: Frame) => void }).write(frame);
  }
}
