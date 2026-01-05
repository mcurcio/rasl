/**
 * Matrix multiplication transform node.
 *
 * Applies a fixed matrix to every channel vector.
 */

import { ErrorCodes, RaslError } from "@rasl/engine";

import { BaseNode, InputPortSpec, MatrixPayload, node, OutputPortSpec, PortGroup } from "../../runtime/index.js";
import type { ITickContext } from "../../runtime/tick.js";

/**
 * Configuration for MatrixMultiplyNode.
 */
export interface IMatrixMultiplyConfig {
  id: string;
  /** Square transformation matrix (rows must match columns) */
  matrix: number[][];
}

/**
 * Transform node that applies a fixed matrix to every channel vector.
 */
@node("MatrixMultiplyNode", "MatrixMultiply")
export class MatrixMultiplyNode extends BaseNode {
  readonly inputs = PortGroup.inputs({
    input: new InputPortSpec({ accepts: "matrix" }),
  });

  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: "matrix" }),
  });

  private readonly _matrix: Float32Array;
  private readonly _size: number;

  constructor(config: IMatrixMultiplyConfig) {
    super({ id: config.id });

    const matrix = config.matrix;
    if (matrix.length === 0) {
      throw new RaslError(ErrorCodes.InvalidArgument, "matrix must contain at least one row");
    }

    const size = matrix.length;
    for (let i = 0; i < size; i++) {
      if (matrix[i].length !== size) {
        throw new RaslError(
          ErrorCodes.InvalidArgument,
          `matrix row ${i} has ${matrix[i].length} columns, expected ${size} (square matrix required)`,
        );
      }
    }

    this._size = size;
    this._matrix = new Float32Array(size * size);
    for (let row = 0; row < size; row++) {
      for (let col = 0; col < size; col++) {
        this._matrix[row * size + col] = matrix[row][col];
      }
    }
  }

  override async pull(_tick: ITickContext): Promise<void> {
    const inputPort = this.inputs.get("input");
    if (!inputPort) return;

    const frame = inputPort.read();
    if (!frame) return;

    const payload = frame.payload as MatrixPayload;
    const data = payload.data;
    const channels = payload.channels;
    const count = payload.count;

    if (channels !== this._size) {
      throw new RaslError(
        ErrorCodes.InvalidArgument,
        `Configured matrix size ${this._size} but payload has ${channels} channels`,
      );
    }

    // Apply matrix multiplication: result = data @ matrix
    const result = new Float32Array(count * channels);
    for (let row = 0; row < count; row++) {
      for (let outCol = 0; outCol < channels; outCol++) {
        let sum = 0;
        for (let k = 0; k < channels; k++) {
          sum += data[row * channels + k] * this._matrix[k * channels + outCol];
        }
        result[row * channels + outCol] = sum;
      }
    }

    const newPayload = new MatrixPayload(result, channels);
    const outputPort = this.outputs.get("out");
    if (outputPort) {
      outputPort.write(frame.withPayload(newPayload));
    }
  }
}
