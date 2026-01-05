/**
 * Random channel mapping transform node.
 *
 * Randomly maps input channels to output channels using a seeded RNG.
 */

import { ErrorCodes, RaslError } from "@rasl/engine";

import { BaseNode, InputPortSpec, MatrixPayload, node,OutputPortSpec, PortGroup } from "../../runtime/index.js";
import type { ITickContext } from "../../runtime/tick.js";

/**
 * Configuration for RandomMapNode.
 */
export interface IRandomMapConfig {
  id: string;
  /** Number of output channels/elements; defaults to input count */
  channelCount?: number;
  /** Optional random seed for deterministic mappings */
  seed?: number;
}

/**
 * Simple seeded PRNG (xorshift32).
 */
function createRng(seed: number): () => number {
  let state = seed >>> 0 || 1;
  return () => {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    return (state >>> 0) / 0xffffffff;
  };
}

/**
 * Transform node that randomly maps input channels to output channels.
 */
@node("RandomMapNode", "RandomMap")
export class RandomMapNode extends BaseNode {
  readonly inputs = PortGroup.inputs({
    input: new InputPortSpec({ accepts: "matrix" }),
  });

  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: "matrix" }),
  });

  private readonly _channelOverride: number | undefined;
  private readonly _seed: number;
  private _inputCount: number | null = null;
  private _outputCount: number | null = null;
  private _mapping: Uint32Array | null = null;

  constructor(config: IRandomMapConfig) {
    super({ id: config.id });
    this._channelOverride = config.channelCount;
    this._outputCount = config.channelCount ?? null;
    this._seed = config.seed ?? Math.floor(Math.random() * 0xffffffff);
  }

  override async pull(_tick: ITickContext): Promise<void> {
    const inputPort = this.inputs.get("input");
    if (!inputPort) return;

    const frame = inputPort.read();
    if (!frame) return;

    const payload = frame.payload as MatrixPayload;
    const data = payload.data;
    const channels = payload.channels;
    const inputCount = payload.count;

    if (inputCount <= 0) {
      throw new RaslError(ErrorCodes.InvalidArgument, "RandomMap requires payloads with at least one element");
    }

    this._validateInputCount(inputCount);
    this._ensureMapping(inputCount);

    const mapping = this._mapping!;
    const outputCount = this._outputCount!;

    // Map rows according to mapping
    const result = new Float32Array(outputCount * channels);
    for (let i = 0; i < outputCount; i++) {
      const srcRow = mapping[i];
      for (let c = 0; c < channels; c++) {
        result[i * channels + c] = data[srcRow * channels + c];
      }
    }

    const newPayload = new MatrixPayload(result, channels);
    const outputPort = this.outputs.get("out");
    if (outputPort) {
      outputPort.write(frame.withPayload(newPayload));
    }
  }

  private _validateInputCount(inputCount: number): void {
    if (this._inputCount === null) {
      this._inputCount = inputCount;
      return;
    }
    if (inputCount !== this._inputCount) {
      throw new RaslError(
        ErrorCodes.InvalidArgument,
        `RandomMap input channel count changed from ${this._inputCount} to ${inputCount}`,
      );
    }
  }

  private _ensureMapping(inputCount: number): void {
    if (this._mapping !== null) return;

    const outputCount = this._channelOverride ?? inputCount;
    if (outputCount <= 0) {
      throw new RaslError(ErrorCodes.InvalidArgument, "RandomMap channelCount must be positive");
    }
    if (inputCount <= 0) {
      throw new RaslError(ErrorCodes.InvalidArgument, "RandomMap requires at least one input channel");
    }

    this._outputCount = outputCount;
    this._mapping = new Uint32Array(outputCount);

    const rng = createRng(this._seed);
    for (let i = 0; i < outputCount; i++) {
      this._mapping[i] = Math.floor(rng() * inputCount);
    }
  }
}
