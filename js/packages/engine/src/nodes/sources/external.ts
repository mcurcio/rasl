import { ErrorCodes, RaslError } from "../../errors.js";
import { BaseNode } from "../base.js";
import { node } from "../registry.js";
import { OutputPortSpec, PortGroup } from "../ports/index.js";
import { Frame } from "../../runtime/frame.js";
import { MatrixPayload } from "../../runtime/payloads/index.js";
import type { ITickContext } from "../../runtime/tick.js";

export interface IExternalSourceConfig {
  id: string;
  size: number;
  channels?: number;
  initial?: number | number[] | string;
  topic?: string;
}

export interface IExternalWritableNode {
  setExternalValues(values: Float32Array): void;
}

export function isExternalWritableNode(node: unknown): node is IExternalWritableNode {
  return typeof (node as { setExternalValues?: unknown }).setExternalValues === "function";
}

function parseInitial(initial: number | number[] | string | undefined): number[] | null {
  if (initial === undefined) return null;
  if (typeof initial === "number") return [initial];
  if (Array.isArray(initial)) return initial;
  return initial
    .trim()
    .split(/\s+/)
    .filter((part) => part.length > 0)
    .map((part) => Number(part));
}

function validateValues(values: Float32Array | number[], expectedSize: number): Float32Array {
  if (values.length !== expectedSize) {
    throw new RaslError(ErrorCodes.InvalidArgument, `ExternalSource expected ${expectedSize} values, got ${values.length}`);
  }

  const out = values instanceof Float32Array ? new Float32Array(values) : new Float32Array(values);
  for (let i = 0; i < out.length; i++) {
    const value = out[i]!;
    if (!Number.isFinite(value) || value < 0 || value > 1) {
      throw new RaslError(ErrorCodes.InvalidArgument, `ExternalSource value at index ${i} must be in [0, 1]`);
    }
  }
  return out;
}

@node("ExternalSourceNode", "ExternalSource")
export class ExternalSourceNode extends BaseNode implements IExternalWritableNode {
  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: "matrix" }),
  });

  private readonly _size: number;
  private readonly _channels: number;
  private readonly _topic: string;
  private _values: Float32Array;

  constructor(config: IExternalSourceConfig) {
    super(config);

    this._size = Number(config.size);
    this._channels = Number(config.channels ?? 1);
    this._topic = config.topic ?? `external.${config.id}`;

    if (!Number.isInteger(this._size) || this._size <= 0) {
      throw new RaslError(ErrorCodes.InvalidArgument, "ExternalSource size must be a positive integer");
    }
    if (!Number.isInteger(this._channels) || this._channels <= 0) {
      throw new RaslError(ErrorCodes.InvalidArgument, "ExternalSource channels must be a positive integer");
    }
    if (this._size % this._channels !== 0) {
      throw new RaslError(ErrorCodes.InvalidArgument, "ExternalSource size must be divisible by channels");
    }

    const initial = parseInitial(config.initial);
    if (initial === null) {
      this._values = new Float32Array(this._size);
    } else if (initial.length === 1) {
      const value = validateValues(initial, 1)[0]!;
      this._values = new Float32Array(this._size);
      this._values.fill(value);
    } else {
      this._values = validateValues(initial, this._size);
    }
  }

  setExternalValues(values: Float32Array): void {
    this._values = validateValues(values, this._size);
  }

  override async pull(tick: ITickContext): Promise<void> {
    this.outputs.get("out")?.write(
      new Frame({
        topic: this._topic,
        timestamp: tick.wallTime,
        payload: new MatrixPayload(this._values, this._channels),
        metadata: this._metadata,
      }),
    );
  }
}
