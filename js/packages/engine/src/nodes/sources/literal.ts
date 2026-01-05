/**
 * Literal source node - produces time-invariant payloads.
 *
 * Outputs a constant payload parsed from config. The literal value is
 * computed once at construction and returned unchanged on every pull.
 */

import { BaseNode, PortGroup, OutputPortSpec, MatrixPayload, Frame, EMPTY_METADATA, node } from '../../runtime/index.js';
import type { ITickContext } from '../../runtime/tick.js';

/**
 * Configuration for LiteralNode.
 */
export interface ILiteralConfig {
  id: string;
  /** The literal value as a flat array or nested array */
  value: number[] | number[][];
  /** Number of channels per element (default: inferred from value) */
  channels?: number;
}

/**
 * Source node that outputs a constant literal payload.
 *
 * LiteralNode wraps a constant value in a MatrixPayload and returns
 * it unchanged on every pull.
 */
@node('LiteralNode', 'Literal')
export class LiteralNode extends BaseNode {
  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: 'matrix' }),
  });

  private readonly _payload: MatrixPayload;
  private readonly _topic: string;

  constructor(config: ILiteralConfig) {
    super({ id: config.id });

    const value = config.value;
    let data: Float32Array;
    let channels: number;

    if (value.length === 0) {
      throw new Error('LiteralNode value cannot be empty');
    }

    // Check if nested array
    if (Array.isArray(value[0])) {
      // Nested array: [[1,2,3], [4,5,6]] -> count=2, channels=3
      const nested = value as number[][];
      channels = config.channels ?? nested[0].length;
      const count = nested.length;
      data = new Float32Array(count * channels);
      for (let i = 0; i < count; i++) {
        const row = nested[i];
        for (let j = 0; j < channels; j++) {
          data[i * channels + j] = j < row.length ? row[j] : 0;
        }
      }
    } else {
      // Flat array
      const flat = value as number[];
      channels = config.channels ?? 1;
      data = new Float32Array(flat);
    }

    this._payload = new MatrixPayload(data, channels);
    this._topic = `literal.${config.id}`;
  }

  override async pull(_tick: ITickContext): Promise<void> {
    const frame = new Frame({
      topic: this._topic,
      timestamp: performance.now() / 1000,
      payload: this._payload,
      metadata: EMPTY_METADATA,
    });

    const outputPort = this.outputs.get('out');
    if (outputPort) {
      outputPort.write(frame);
    }
  }
}
