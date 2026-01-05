/**
 * GoveeLightNode - Sink node that streams ColorPayloads to a Govee light via LAN TCP.
 */

import {
  BaseNode,
  type ITickContext,
  InputPort,
  InputPortSpec,
  MatrixPayload,
  type NodeContext,
  PortGroup,
  node,
  pullRate,
} from '@rasl/engine';
import {
  GoveeLightClient,
  DEFAULT_GOVEE_PORT,
  type IGoveeColor,
  type IGoveeDeviceInfo,
  type IGoveeSegmentColor,
  type IGoveeSegmentInfo,
} from './client.js';

export interface IGoveeLightNodeConfig {
  id: string;
  host: string;
  port?: number;
  fps?: number | string;
  inputPort?: string;
  segmentChannels?: number;
}

function parseFps(fps: unknown): number {
  if (typeof fps === 'number') return fps;
  if (typeof fps === 'string') {
    const lower = fps.toLowerCase();
    if (lower.endsWith('hz')) {
      return parseFloat(lower.slice(0, -2));
    } else if (lower.endsWith('ms')) {
      return 1000 / parseFloat(lower.slice(0, -2));
    }
    return parseFloat(fps);
  }
  return 20;
}

@node('GoveeLightNode', 'GoveeLight')
export class GoveeLightNode extends BaseNode {
  readonly inputs: PortGroup<InputPort>;

  private readonly _host: string;
  private readonly _port: number;
  private readonly _fps: number;
  private readonly _inputPort: string;
  private readonly _segmentChannelsOverride: number | null;

  private _client: GoveeLightClient | null = null;
  private _ctx: NodeContext | null = null;
  private _segments: IGoveeSegmentInfo[] = [];
  private _segmentCount: number | null = null;
  private _channelsPerSegment: number;

  private _framesSent = 0;
  private _framesDropped = 0;

  constructor(config: IGoveeLightNodeConfig) {
    super(config);
    this._host = config.host;
    this._port = config.port ?? DEFAULT_GOVEE_PORT;
    this._fps = parseFps(config.fps);
    this._inputPort = config.inputPort ?? 'light';
    this._segmentChannelsOverride = config.segmentChannels ?? null;
    this._channelsPerSegment = this._segmentChannelsOverride ?? 3;

    this.inputs = PortGroup.inputs({
      [this._inputPort]: new InputPortSpec({ accepts: ['matrix', 'color'] }),
    });
  }

  override async start(ctx: NodeContext): Promise<void> {
    this._ctx = ctx;
    this._client = new GoveeLightClient(this._host, this._port);

    let info: IGoveeDeviceInfo | null = null;
    try {
      info = await this._client.discover();
    } catch (err) {
      ctx.logger.warn(
        `GoveeLight '${this.id}' discovery failed: ${err}`
      );
    }

    if (info !== null) {
      if (info.segments.length > 0) {
        this._segments = info.segments;
        this._segmentCount = info.segments.length;
      }
      const detectedChannels = info.channelsPerSegment;
      if (this._segmentChannelsOverride !== null) {
        this._channelsPerSegment = this._segmentChannelsOverride;
      } else {
        this._channelsPerSegment = detectedChannels;
      }
    }

    if (this._channelsPerSegment !== 3 && this._channelsPerSegment !== 4) {
      ctx.logger.warn(
        `GoveeLight '${this.id}' invalid channel count ${this._channelsPerSegment}, defaulting to 3`
      );
      this._channelsPerSegment = 3;
    }

    ctx.logger.info(
      `GoveeLight '${this.id}' started: ${this._host}:${this._port} at ${this._fps} FPS, ` +
      `segments=${this._segmentCount ?? 'unknown'}, channels=${this._channelsPerSegment}`
    );
  }

  override async stop(ctx: NodeContext): Promise<void> {
    if (this._client !== null) {
      this._client.close();
      this._client = null;
    }

    ctx.logger.info(
      `GoveeLight '${this.id}' stopped: ${this._framesSent} sent, ${this._framesDropped} dropped`
    );
  }

  @pullRate((self: unknown) => (self as GoveeLightNode)._fps)
  override async pull(tick: ITickContext): Promise<void> {
    if (this._client === null) return;

    const inPort = this.inputs.get(this._inputPort);
    const frame = inPort?.read() ?? null;
    if (!frame) return;

    const payload = frame.payload as MatrixPayload;
    const data = payload.data;

    // Validate shape: [count, channels]
    const rows = payload.count;
    const cols = payload.channels;

    if (cols !== this._channelsPerSegment) {
      this._framesDropped++;
      if (this._ctx) {
        this._ctx.logger.warn(
          `GoveeLight '${this.id}' channel mismatch: expected ${this._channelsPerSegment}, got ${cols}`
        );
      }
      return;
    }

    // Check segment count consistency
    if (this._segmentCount !== null && rows !== this._segmentCount) {
      this._framesDropped++;
      if (this._ctx) {
        this._ctx.logger.warn(
          `GoveeLight '${this.id}' segment mismatch: expected ${this._segmentCount}, got ${rows}`
        );
      }
      return;
    }

    // Initialize segment count on first frame
    if (this._segmentCount === null) {
      this._segmentCount = rows;
      if (this._segments.length === 0) {
        this._segments = Array.from({ length: rows }, (_, i) => ({ segmentId: i }));
      }
    }

    // Quantize to uint8
    const byteMatrix = this._quantizePayload(data, rows, cols);

    // Build segment payload
    const segmentIds = this._resolveSegmentIds(rows);
    if (segmentIds === null) {
      this._framesDropped++;
      return;
    }

    const segments = this._buildSegmentPayload(byteMatrix, segmentIds, cols);
    const topColor = this._rowToColor(byteMatrix, 0, cols);

    try {
      this._client.sendColorCommand(topColor, segments);
      this._framesSent++;
    } catch (err) {
      this._framesDropped++;
      if (this._ctx) {
        this._ctx.logger.error(
          `GoveeLight '${this.id}' send failed: ${err}`
        );
      }
    }

    void tick;
  }

  private _quantizePayload(data: Float32Array, rows: number, cols: number): Uint8Array {
    const result = new Uint8Array(rows * cols);
    for (let i = 0; i < data.length; i++) {
      const clamped = Math.max(0, Math.min(1, data[i]));
      result[i] = Math.round(clamped * 255);
    }
    return result;
  }

  private _resolveSegmentIds(count: number): number[] | null {
    if (this._segments.length > 0 && this._segments.length === count) {
      return this._segments.map((s) => s.segmentId);
    }
    if (this._segments.length > 0 && this._segments.length !== count) {
      if (this._ctx) {
        this._ctx.logger.warn(
          `GoveeLight '${this.id}' segment count changed: discovered ${this._segments.length}, received ${count}`
        );
      }
      return null;
    }
    return Array.from({ length: count }, (_, i) => i);
  }

  private _buildSegmentPayload(
    byteMatrix: Uint8Array,
    segmentIds: number[],
    cols: number
  ): IGoveeSegmentColor[] {
    const segments: IGoveeSegmentColor[] = [];
    for (let i = 0; i < segmentIds.length; i++) {
      const color = this._rowToColor(byteMatrix, i, cols);
      segments.push({ segmentId: segmentIds[i], ...color });
    }
    return segments;
  }

  private _rowToColor(byteMatrix: Uint8Array, row: number, cols: number): IGoveeColor {
    const offset = row * cols;
    const color: IGoveeColor = {
      r: byteMatrix[offset],
      g: byteMatrix[offset + 1],
      b: byteMatrix[offset + 2],
    };
    if (cols >= 4) {
      color.w = byteMatrix[offset + 3];
    }
    return color;
  }
}
