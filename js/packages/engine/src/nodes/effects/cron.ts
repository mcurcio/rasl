/**
 * CronNode - Outputs 0 or 1 based on cron schedule.
 *
 * Simplified implementation that outputs 1 when current minute matches schedule.
 */

import {
  BaseNode,
  Frame,
  type ITickContext,
  MatrixPayload,
  node,
  OutputPortSpec,
  PortGroup,
  pullRate,
} from "../../runtime/index.js";

export interface ICronConfig {
  id: string;
  schedule?: string;
  topic?: string;
  fps?: number;
}

@node("CronNode", "cron")
export class CronNode extends BaseNode {
  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: "matrix" }),
  });

  private readonly _schedule: string;
  private readonly _topic: string;
  private readonly _fps: number;

  constructor(config: ICronConfig) {
    super(config);
    this._schedule = config.schedule ?? "* * * * *";
    this._topic = config.topic ?? `cron.${this.id}`;
    this._fps = config.fps ?? 1;
  }

  @pullRate((self: unknown) => (self as CronNode)._fps)
  override async pull(tick: ITickContext): Promise<void> {
    // Simple implementation: parse schedule and check if current time matches
    // For now, just output alternating 0/1 based on minute
    const now = new Date();
    const minute = now.getMinutes();

    // Parse schedule like "*/2 * * * *" (every 2 minutes)
    let value = 0;
    const parts = this._schedule.split(" ");
    if (parts[0]) {
      const minutePart = parts[0];
      if (minutePart === "*") {
        value = 1;
      } else if (minutePart.startsWith("*/")) {
        const interval = parseInt(minutePart.slice(2), 10);
        value = minute % interval === 0 ? 1 : 0;
      } else {
        const targetMinute = parseInt(minutePart, 10);
        value = minute === targetMinute ? 1 : 0;
      }
    }

    const outData = new Float32Array([value]);
    const outPayload = new MatrixPayload(outData, 1);
    const outFrame = new Frame({
      topic: this._topic,
      timestamp: tick.wallTime,
      payload: outPayload,
      metadata: this._metadata,
    });

    this.outputs.get("out")?.write(outFrame);
  }
}
