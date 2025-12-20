/**
 * Matrix payload types for numeric signal data.
 *
 * MatrixPayload is the base for all numeric signals.
 */

import { FramePayload, type IPayloadDescriptor } from './base.js';

/**
 * Base for all numeric signal types.
 *
 * MatrixPayload represents a 2D numeric matrix with shape (count, channels).
 * This is the universal currency for signal data in RASL.
 *
 * Shape convention:
 * - count: First dimension (number of elements, e.g., number of pixels)
 * - channels: Second dimension (dimensions per element, e.g., 3 for RGB)
 */
export class MatrixPayload extends FramePayload {
  static override readonly domain = 'matrix' as string;

  /**
   * The underlying data array.
   */
  readonly data: Float32Array;

  /**
   * Number of elements (rows).
   */
  readonly count: number;

  /**
   * Number of channels per element (columns).
   */
  readonly channels: number;

  constructor(data: Float32Array | number[], channels = 1) {
    super();
    const arr = data instanceof Float32Array ? data : new Float32Array(data);

    if (channels < 1) {
      throw new Error(`channels must be >= 1, got ${channels}`);
    }

    this.data = arr;
    this.channels = channels;
    this.count = Math.floor(arr.length / channels);
  }

  /**
   * Total number of values (count * channels).
   */
  get size(): number {
    return this.count * this.channels;
  }

  /**
   * Get value at (row, col).
   */
  get(row: number, col = 0): number {
    return this.data[row * this.channels + col];
  }

  /**
   * Get a row as a subarray view.
   */
  getRow(row: number): Float32Array {
    const start = row * this.channels;
    return this.data.subarray(start, start + this.channels);
  }

  /**
   * Flatten to 1D array.
   */
  flatten(): Float32Array {
    return this.data;
  }

  /**
   * Repeat the payload n times.
   */
  repeat(n: number): MatrixPayload {
    if (n <= 1) return this;

    const newData = new Float32Array(this.data.length * n);
    for (let i = 0; i < n; i++) {
      newData.set(this.data, i * this.data.length);
    }
    return new MatrixPayload(newData, this.channels);
  }

  override describe(): IPayloadDescriptor {
    return {
      typeName: 'MatrixPayload',
      domain: MatrixPayload.domain,
      attrs: {
        count: this.count,
        channels: this.channels,
        size: this.size,
      },
    };
  }

  /**
   * MatrixPayload accepts any MatrixPayload subclass.
   */
  static override isCompatibleWith(other: typeof FramePayload): boolean {
    return other.prototype instanceof MatrixPayload || (other as unknown) === MatrixPayload;
  }
}

/**
 * Boolean/mask payload.
 * Values are normalized to 0.0 or 1.0.
 */
export class BoolPayload extends MatrixPayload {
  static override readonly domain = 'bool' as string;

  constructor(data: Float32Array | number[] | boolean[]) {
    const arr = Array.isArray(data)
      ? new Float32Array(data.map((v) => (v ? 1.0 : 0.0)))
      : new Float32Array(data.length);

    if (data instanceof Float32Array) {
      for (let i = 0; i < data.length; i++) {
        arr[i] = data[i] !== 0 ? 1.0 : 0.0;
      }
    }

    super(arr, 1);
  }

  override describe(): IPayloadDescriptor {
    return {
      typeName: 'BoolPayload',
      domain: BoolPayload.domain,
      attrs: {
        count: this.count,
        channels: this.channels,
      },
    };
  }
}
