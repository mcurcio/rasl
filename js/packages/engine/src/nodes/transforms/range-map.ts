/**
 * Range mapping transform node.
 *
 * Remaps each channel from a configured source range to [0, 1].
 */

import { ErrorCodes, RaslError } from "@rasl/engine";

import { BaseNode, InputPortSpec, MatrixPayload, node,OutputPortSpec, PortGroup } from "../../runtime/index.js";
import type { ITickContext } from "../../runtime/tick.js";

/**
 * Configuration for RangeMapNode.
 */
export interface IRangeMapConfig {
  id: string;
  /** Per-channel [min, max] source ranges */
  ranges: [number, number][];
  /** Clamp inputs to the configured range before remapping (default: true) */
  clamp?: boolean;
}

/**
 * Transform node that remaps each channel to a configured range.
 */
@node("RangeMapNode", "RangeMap")
export class RangeMapNode extends BaseNode {
  readonly inputs = PortGroup.inputs({
    input: new InputPortSpec({ accepts: "matrix" }),
  });

  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: "matrix" }),
  });

  private readonly _mins: Float32Array;
  private readonly _maxs: Float32Array;
  private readonly _spans: Float32Array;
  private readonly _clamp: boolean;
  private readonly _channelCount: number;

  constructor(config: IRangeMapConfig) {
    super({ id: config.id });

    const ranges = config.ranges;
    if (ranges.length === 0) {
      throw new RaslError(ErrorCodes.InvalidArgument, "RangeMapNode requires at least one range");
    }

    this._channelCount = ranges.length;
    this._mins = new Float32Array(ranges.length);
    this._maxs = new Float32Array(ranges.length);
    this._spans = new Float32Array(ranges.length);
    this._clamp = config.clamp ?? true;

    for (let i = 0; i < ranges.length; i++) {
      const [low, high] = ranges[i];
      if (high <= low) {
        throw new RaslError(ErrorCodes.InvalidArgument, `ranges[${i}] max (${high}) must be greater than min (${low})`);
      }
      this._mins[i] = low;
      this._maxs[i] = high;
      this._spans[i] = high - low;
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

    // Validate channel count matches
    if (channels !== this._channelCount) {
      throw new RaslError(
        ErrorCodes.InvalidArgument,
        `Configured ${this._channelCount} ranges but payload has ${channels} channels`,
      );
    }

    // Apply range mapping
    const result = new Float32Array(data.length);
    const count = payload.count;

    for (let row = 0; row < count; row++) {
      for (let col = 0; col < channels; col++) {
        const idx = row * channels + col;
        let value = data[idx];

        if (this._clamp) {
          value = Math.max(this._mins[col], Math.min(this._maxs[col], value));
        }

        result[idx] = (value - this._mins[col]) / this._spans[col];
      }
    }

    const newPayload = new MatrixPayload(result, channels);
    const outputPort = this.outputs.get("out");
    if (outputPort) {
      outputPort.write(frame.withPayload(newPayload));
    }
  }
}
