/**
 * LifxSinkNode - Sink node that streams ColorPayloads to LIFX lights via LAN UDP.
 */

import type {
  InputPort,
  MatrixPayload} from "@rasl/engine";
import {
  BaseNode,
  ErrorCodes,
  InputPortSpec,
  type ITickContext,
  node,
  type NodeContext,
  PortGroup,
  pullRate,
  RaslError,
} from "@rasl/engine";

import { hsbkToLifx, type ILifxEndpoint,LifxLanClient, parseTargetList } from "./client.js";

export interface ILifxSinkNodeConfig {
  id: string;
  target: string;
  fps?: number | string;
  durationMs?: number;
  rapid?: boolean;
  logUnresolvedIntervalS?: number;
}

function parseFps(fps: unknown): number {
  if (typeof fps === "number") return fps;
  if (typeof fps === "string") {
    const lower = fps.toLowerCase();
    if (lower.endsWith("hz")) {
      return parseFloat(lower.slice(0, -2));
    } else if (lower.endsWith("ms")) {
      return 1000 / parseFloat(lower.slice(0, -2));
    }
    return parseFloat(fps);
  }
  return 30;
}

@node("LifxSinkNode", "LifxSink")
export class LifxSinkNode extends BaseNode {
  readonly inputs: PortGroup<InputPort>;

  private readonly _endpoints: ILifxEndpoint[];
  private readonly _fps: number;
  private readonly _durationMs: number;
  private readonly _rapid: boolean;
  private readonly _logInterval: number;

  private _clients: LifxLanClient[] = [];
  private _ctx: NodeContext | null = null;
  private _framesSent = 0;
  private _framesDropped = 0;
  private _lastUnresolvedLog = 0;

  constructor(config: ILifxSinkNodeConfig) {
    super(config);

    this._endpoints = parseTargetList(config.target);
    if (this._endpoints.length === 0) {
      throw new RaslError(ErrorCodes.InvalidArgument, "target must include at least one IP address");
    }

    this._fps = parseFps(config.fps);
    this._durationMs = config.durationMs ?? 0;
    this._rapid = config.rapid ?? false;
    this._logInterval = (config.logUnresolvedIntervalS ?? 5) * 1000;

    this.inputs = PortGroup.inputs({
      color: new InputPortSpec({ accepts: ["matrix", "color"] }),
    });
  }

  override async start(ctx: NodeContext): Promise<void> {
    this._ctx = ctx;
    this._clients = [];
    let failures = 0;

    for (const endpoint of this._endpoints) {
      const client = new LifxLanClient(endpoint);
      try {
        await client.start();
        this._clients.push(client);
      } catch (err) {
        failures++;
        ctx.logger.error(`LifxSink '${this.id}' client start failed: ${endpoint.ip}:${endpoint.port} - ${err}`);
      }
    }

    ctx.logger.info(
      `LifxSink '${this.id}' started: ${this._clients.length} targets, ${failures} failed, ${this._fps} FPS`,
    );
  }

  override async stop(ctx: NodeContext): Promise<void> {
    for (const client of this._clients) {
      client.stop();
    }
    this._clients = [];

    ctx.logger.info(`LifxSink '${this.id}' stopped: ${this._framesSent} sent, ${this._framesDropped} dropped`);
    this._ctx = null;
  }

  @pullRate((self: unknown) => (self as LifxSinkNode)._fps)
  override async pull(tick: ITickContext): Promise<void> {
    const inPort = this.inputs.get("color");
    const frame = inPort?.read() ?? null;
    if (!frame) return;

    const payload = frame.payload as MatrixPayload;
    const data = payload.data;
    const rows = payload.count;
    const cols = payload.channels;

    // HSBK requires 4 channels
    if (cols !== 4) {
      this._framesDropped++;
      if (this._ctx) {
        this._ctx.logger.warn(`LifxSink '${this.id}' channel mismatch: expected 4 (HSBK), got ${cols}`);
      }
      return;
    }

    const clients = this._clients;
    if (clients.length === 0) {
      this._framesDropped++;
      this._maybeLogUnresolved();
      return;
    }

    const assignments = this._buildAssignments(rows, clients.length);
    if (assignments.length === 0) {
      this._framesDropped++;
      return;
    }

    let sentAny = false;
    for (const [clientIdx, rowIdx] of assignments) {
      const client = clients[clientIdx];
      const offset = rowIdx * cols;
      const h = data[offset];
      const s = data[offset + 1];
      const b = data[offset + 2];
      const k = data[offset + 3];

      const lifxColor = hsbkToLifx(h, s, b, k);

      try {
        client.sendSetColor(
          lifxColor.hue,
          lifxColor.saturation,
          lifxColor.brightness,
          lifxColor.kelvin,
          this._durationMs,
          this._rapid,
        );
        sentAny = true;
      } catch (err) {
        if (this._ctx) {
          const desc = client.describe();
          this._ctx.logger.error(`LifxSink '${this.id}' send failed: ${desc.ip}:${desc.port} - ${err}`);
        }
      }
    }

    if (sentAny) {
      this._framesSent++;
    } else {
      this._framesDropped++;
    }

    void tick;
  }

  private _buildAssignments(rows: number, clientCount: number): [number, number][] {
    if (rows === 0 || clientCount === 0) {
      return [];
    }

    // 1:1 mapping
    if (rows === clientCount) {
      return Array.from({ length: rows }, (_, i) => [i, i] as [number, number]);
    }

    // Single row broadcasts to all clients
    if (rows === 1) {
      return Array.from({ length: clientCount }, (_, i) => [i, 0] as [number, number]);
    }

    // Single client gets first row
    if (clientCount === 1) {
      return [[0, 0]];
    }

    // Mismatch - log warning
    if (this._ctx) {
      this._ctx.logger.warn(`LifxSink '${this.id}' payload/target mismatch: ${rows} rows, ${clientCount} targets`);
    }
    return [];
  }

  private _maybeLogUnresolved(): void {
    const now = Date.now();
    if (now - this._lastUnresolvedLog < this._logInterval) {
      return;
    }
    this._lastUnresolvedLog = now;
    if (this._ctx) {
      this._ctx.logger.warn(
        `LifxSink '${this.id}' no active targets: configured ${this._endpoints.length}, active ${this._clients.length}`,
      );
    }
  }
}
