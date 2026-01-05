/**
 * LiteralNode - Source node that outputs constant literal payloads.
 *
 * Parses a literal value from config and wraps it in the appropriate
 * payload type. The payload is computed once at construction and
 * returned unchanged on every pull.
 */

import {
  BaseNode,
  Frame,
  type ITickContext,
  MatrixPayload,
  node,
  type OutputPort,
  OutputPortSpec,
  PortGroup,
  pullRate,
} from "@rasl/engine";

import type { ColorModel } from "../../convert.js";
import { ColorPayload } from "../transforms/color.js";

export interface ILiteralConfig {
  id: string;
  /** Payload kind (color, matrix) */
  payloadKind?: string;
  /** Payload subtype (hsl, oklch, srgb, etc.) */
  payloadSubtype?: string;
  /** Literal data as string or parsed array */
  data?: string | number[] | number[][];
  /** Combined model string like "color:hsl" */
  model?: string;
  /** Topic for output frames */
  topic?: string;
  /** Output FPS */
  fps?: number;
}

function parseLiteral(value: string | number[] | number[][]): number[] | number[][] {
  if (typeof value === "string") {
    try {
      return JSON.parse(value) as number[] | number[][];
    } catch {
      // Try parsing as space-separated numbers
      const nums = value
        .split(/[\s,]+/)
        .map(Number)
        .filter((n) => !isNaN(n));
      return nums;
    }
  }
  return value;
}

function buildPayload(kind: string, subtype: string | undefined, value: number[] | number[][]): MatrixPayload {
  // Flatten nested arrays
  let flat: Float32Array;
  let channels = 1;

  if (Array.isArray(value[0])) {
    // Nested array like [[h,s,l], [h,s,l], ...]
    const nested = value as number[][];
    channels = nested[0]?.length ?? 1;
    flat = new Float32Array(nested.length * channels);
    for (let i = 0; i < nested.length; i++) {
      for (let j = 0; j < channels; j++) {
        flat[i * channels + j] = nested[i][j] ?? 0;
      }
    }
  } else {
    // Flat array
    flat = new Float32Array(value as number[]);
  }

  if (kind === "color") {
    const model = (subtype ?? "srgb") as ColorModel;
    return new ColorPayload(flat, channels, model);
  }

  return new MatrixPayload(flat, channels);
}

@node("LiteralNode", "literal")
export class LiteralNode extends BaseNode {
  readonly outputs: PortGroup<OutputPort> = PortGroup.outputs({
    out: new OutputPortSpec({ produces: "matrix" }),
  });

  private readonly _payload: MatrixPayload;
  private readonly _topic: string;
  private readonly _fps: number;

  constructor(config: ILiteralConfig) {
    super(config);

    // Parse model from "color:hsl" format or separate fields
    let kind = config.payloadKind ?? "matrix";
    let subtype = config.payloadSubtype;

    if (config.model) {
      const parts = config.model.split(":");
      kind = parts[0] ?? "matrix";
      subtype = parts[1];
    }

    // Parse literal data
    const data = config.data ?? [];
    const parsed = parseLiteral(data);

    this._payload = buildPayload(kind, subtype, parsed);
    this._topic = config.topic ?? `literal.${this.id}`;
    this._fps = config.fps ?? 30;
  }

  @pullRate((self: unknown) => (self as LiteralNode)._fps)
  override async pull(tick: ITickContext): Promise<void> {
    const frame = new Frame({
      topic: this._topic,
      timestamp: tick.wallTime,
      payload: this._payload,
      metadata: this._metadata,
    });

    this.outputs.get("out")?.write(frame);
  }
}
