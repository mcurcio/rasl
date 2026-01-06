/**
 * ConsoleSink - Debug output to console.
 */

import type { MatrixPayload } from "../../runtime/index.js";
import {
  BaseNode,
  type ILogger,
  InputPortSpec,
  type ITickContext,
  node,
  type NodeContext,
  PortGroup,
  pullRate,
} from "../../runtime/index.js";

function payloadHasModel(payload: MatrixPayload): boolean {
  return Object.prototype.hasOwnProperty.call(payload, "model");
}

export interface IConsoleSinkConfig {
  id: string;
  fps?: number;
  format?: "compact" | "full" | "hex";
  maxValues?: number;

  // Config keys used by existing RASL configs
  max_channels?: number;
  as_bytes?: boolean;
  include_metadata?: boolean;
}

@node("ConsoleSink", "Console")
export class ConsoleSink extends BaseNode {
  readonly inputs = PortGroup.inputs({
    in: new InputPortSpec({ accepts: ["matrix", "color"] }),
  });

  private readonly _fps: number;
  private readonly _format: "compact" | "full" | "hex";
  private readonly _maxValues: number;
  private readonly _asBytes: boolean;
  private readonly _includeMetadata: boolean;
  private _logger: ILogger | null = null;

  constructor(config: IConsoleSinkConfig) {
    super(config);
    this._fps = config.fps ?? 30;
    this._format = config.format ?? "compact";
    this._maxValues = config.maxValues ?? config.max_channels ?? 10;
    this._asBytes = config.as_bytes ?? false;
    this._includeMetadata = config.include_metadata ?? false;
  }

  override async start(ctx: NodeContext): Promise<void> {
    this._logger = ctx.logger;
    ctx.logger.info(`ConsoleSink '${this.id}' started at ${this._fps} FPS`);
  }

  @pullRate((self: unknown) => (self as ConsoleSink)._fps)
  override async pull(tick: ITickContext): Promise<void> {
    const inPort = this.inputs.get("in");
    const frame = inPort?.read() ?? null;
    if (!frame) return;

    const payload = frame.payload as MatrixPayload;
    if (this._logger) {
      this._logger.debug("ConsoleSink payload", { descriptor: payload.describe() });
    }
    const data = payload.flatten();

    let output: string;
    const isColor = payloadHasModel(payload) || payload.describe().domain === "color";

    if (isColor) {
      output = this._formatColor(payload);
    } else {
      switch (this._format) {
        case "hex":
          output = this._formatHex(data);
          break;
        case "full":
          output = this._formatFull(data);
          break;
        case "compact":
        default:
          output = this._formatCompact(data);
      }
    }

    const meta = this._includeMetadata ? { topic: frame.topic, ts: frame.timestamp } : undefined;
    if (meta) {
      this._logger?.info(`[${this.id}] t=${tick.t.toFixed(2)}s ${output}`, meta);
    } else {
      this._logger?.info(`[${this.id}] t=${tick.t.toFixed(2)}s ${output}`);
    }
  }

  private _formatColor(payload: MatrixPayload): string {
    const data = payload.flatten();
    const channels = payload.channels;
    const count = payload.count;

    if (channels < 3 || data.length < 3) return this._formatCompact(data);

    const limit = Math.min(count, this._maxValues);
    const parts: string[] = [];

    for (let i = 0; i < limit; i++) {
      const r = data[i * channels] ?? 0;
      const g = data[i * channels + 1] ?? 0;
      const b = data[i * channels + 2] ?? 0;

      if (this._asBytes) {
        const rr = Math.max(0, Math.min(255, Math.round(r * 255)));
        const gg = Math.max(0, Math.min(255, Math.round(g * 255)));
        const bb = Math.max(0, Math.min(255, Math.round(b * 255)));
        parts.push(
          `#${rr.toString(16).padStart(2, "0")}${gg.toString(16).padStart(2, "0")}${bb.toString(16).padStart(2, "0")}`,
        );
      } else {
        parts.push(`[${r.toFixed(3)}, ${g.toFixed(3)}, ${b.toFixed(3)}]`);
      }
    }

    const suffix = count > limit ? ` ... (${count} total)` : "";
    return `[${parts.join(", ")}${suffix}]`;
  }

  private _formatCompact(data: Float32Array): string {
    const values = Array.from(data.slice(0, this._maxValues))
      .map((v) => v.toFixed(2))
      .join(", ");
    const suffix = data.length > this._maxValues ? ` ... (${data.length} total)` : "";
    return `[${values}${suffix}]`;
  }

  private _formatFull(data: Float32Array): string {
    return `[${Array.from(data)
      .map((v) => v.toFixed(3))
      .join(", ")}]`;
  }

  private _formatHex(data: Float32Array): string {
    const hexValues = Array.from(data.slice(0, this._maxValues))
      .map((v) =>
        Math.round(v * 255)
          .toString(16)
          .padStart(2, "0"),
      )
      .join("");
    const suffix = data.length > this._maxValues ? `... (${data.length} total)` : "";
    return `#${hexValues} ${suffix}`;
  }
}
