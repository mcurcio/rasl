/**
 * DdpSink - Outputs RGB data via DDP protocol.
 *
 * Transmits RGB pixel data as DDP packets to network devices
 * (LED controllers, WLED, etc.). DDP is optimized for high pixel
 * counts with up to 480 RGB pixels per packet.
 */

import {
  BaseNode,
  Frame,
  type ITickContext,
  InputPortSpec,
  MatrixPayload,
  type NodeContext,
  PortGroup,
  node,
  pullRate,
} from '@rasl/engine';
import { DDPClient } from './client.js';

export interface IDdpSinkConfig {
  id: string;
  target?: string;
  fps?: number;
  maxCount?: number;
  inputPort?: string;
  pushEveryPacket?: boolean;
}

function parseFps(fps: unknown): number {
  if (typeof fps === 'number') return fps;
  if (typeof fps === 'string') {
    // Handle "20hz", "30", "50ms" formats
    const lower = fps.toLowerCase();
    if (lower.endsWith('hz')) {
      return parseFloat(lower.slice(0, -2));
    } else if (lower.endsWith('ms')) {
      return 1000 / parseFloat(lower.slice(0, -2));
    }
    return parseFloat(fps);
  }
  return 30;
}

@node('DdpSinkNode', 'DdpSink')
export class DdpSinkNode extends BaseNode {
  readonly inputs: PortGroup;

  private readonly _target: string;
  private readonly _fps: number;
  private readonly _maxCount: number | null;
  private readonly _inputPort: string;
  private readonly _pushEveryPacket: boolean;
  private _client: DDPClient | null = null;
  private _framesSent = 0;
  private _framesDropped = 0;

  constructor(config: IDdpSinkConfig) {
    super(config);
    this._target = config.target ?? 'localhost';
    this._fps = parseFps(config.fps);
    this._maxCount = config.maxCount ?? null;
    this._inputPort = config.inputPort ?? 'pixels';
    this._pushEveryPacket = config.pushEveryPacket ?? false;

    // Build dynamic input port based on config
    this.inputs = PortGroup.inputs({
      [this._inputPort]: new InputPortSpec({ accepts: ['matrix', 'color'] }),
    });
  }

  override async start(ctx: NodeContext): Promise<void> {
    this._client = new DDPClient(this._target);
    this._client.connect();
    ctx.logger.info(
      `DdpSink '${this.id}' targeting ${this._target} at ${this._fps} FPS`
    );
  }

  override async stop(ctx: NodeContext): Promise<void> {
    if (this._client !== null) {
      this._client.close();
      this._client = null;
    }
    ctx.logger.info(
      `DdpSink '${this.id}' stopped: ${this._framesSent} sent, ${this._framesDropped} dropped`
    );
  }

  @pullRate((self: unknown) => (self as DdpSinkNode)._fps)
  override async pull(tick: ITickContext): Promise<void> {
    if (this._client === null) return;

    const inPort = this.inputs.get(this._inputPort);
    const frame = inPort?.read() ?? null;
    if (!frame) return;

    const payload = frame.payload as MatrixPayload;
    const data = payload.flatten();

    // Convert float [0,1] to uint8 [0,255]
    let byteData = new Uint8Array(data.length);
    for (let i = 0; i < data.length; i++) {
      byteData[i] = Math.round(Math.max(0, Math.min(1, data[i])) * 255);
    }

    // Apply max_count limit
    if (this._maxCount !== null) {
      const channels = payload.channels;
      const maxLen = this._maxCount * channels;
      if (byteData.length > maxLen) {
        byteData = byteData.subarray(0, maxLen);
      }
    }

    if (byteData.length === 0) return;

    try {
      const nextOffset = this._client.sendNonblocking(
        byteData,
        0,
        this._pushEveryPacket
      );
      if (nextOffset === 0) {
        this._framesSent++;
      } else {
        this._framesDropped++;
      }
    } catch (e) {
      // Log error but don't crash
      console.error(`DdpSink '${this.id}' send error:`, e);
    }

    void tick;
  }
}
