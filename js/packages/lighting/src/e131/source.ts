/**
 * SacnSource - Receives sACN/E1.31 DMX data.
 *
 * Listens for sACN (E1.31) DMX packets on the network and emits
 * them as normalized Frames into the processing graph.
 */

import * as dgram from 'node:dgram';
import {
  BaseNode,
  Frame,
  type ITickContext,
  MatrixPayload,
  OutputPortSpec,
  type NodeContext,
  PortGroup,
  node,
} from '@rasl/core';

export interface ISacnSourceConfig {
  id: string;
  bindAddress?: string;
  bindPort?: number;
  universes?: number | number[];
  topic?: string;
}

// sACN E1.31 constants
const SACN_PORT = 5568;
const SACN_HEADER_SIZE = 126; // Root + Framing + DMP layers

function parseUniverses(universes: unknown): number[] {
  if (typeof universes === 'number') return [universes];
  if (Array.isArray(universes)) return universes.map(Number);
  return [1];
}

@node('SacnSourceNode', 'SacnSource')
export class SacnSourceNode extends BaseNode {
  readonly outputs = PortGroup.outputs({
    out: new OutputPortSpec({ produces: 'matrix' }),
  });

  private readonly _bindAddress: string;
  private readonly _bindPort: number;
  private readonly _universes: number[];
  private readonly _topic: string;
  private _socket: dgram.Socket | null = null;
  private _latestData: Float32Array | null = null;

  constructor(config: ISacnSourceConfig) {
    super(config);
    this._bindAddress = config.bindAddress ?? '0.0.0.0';
    this._bindPort = config.bindPort ?? SACN_PORT;
    this._universes = parseUniverses(config.universes);
    this._topic = config.topic ?? `sacn.${this.id}`;
  }

  override async start(ctx: NodeContext): Promise<void> {
    this._socket = dgram.createSocket({ type: 'udp4', reuseAddr: true });

    this._socket.on('message', (msg: Buffer) => {
      this._handlePacket(msg);
    });

    this._socket.on('error', (err: Error) => {
      ctx.logger.error(`SacnSource '${this.id}' error: ${err.message}`);
    });

    await new Promise<void>((resolve, reject) => {
      this._socket!.bind(this._bindPort, this._bindAddress, () => {
        ctx.logger.info(
          `SacnSource '${this.id}' listening on ${this._bindAddress}:${this._bindPort} for universes ${this._universes.join(', ')}`
        );
        resolve();
      });
      this._socket!.once('error', reject);
    });
  }

  override async stop(ctx: NodeContext): Promise<void> {
    if (this._socket !== null) {
      this._socket.close();
      this._socket = null;
    }
    ctx.logger.info(`SacnSource '${this.id}' stopped`);
  }

  private _handlePacket(msg: Buffer): void {
    // Validate minimum packet size
    if (msg.length < SACN_HEADER_SIZE + 1) return;

    // Check ACN packet identifier (bytes 4-15)
    const acnId = msg.toString('ascii', 4, 16);
    if (acnId !== 'ASC-E1.17\0\0\0') return;

    // Extract universe number (bytes 113-114, big-endian)
    const universe = msg.readUInt16BE(113);

    // Check if this universe is one we're listening for
    if (!this._universes.includes(universe)) return;

    // Extract DMX data (starts at byte 126)
    const dmxStart = SACN_HEADER_SIZE;
    const dmxLength = Math.min(512, msg.length - dmxStart);
    if (dmxLength <= 0) return;

    // Normalize DMX bytes (0-255) to float32 (0.0-1.0)
    const data = new Float32Array(dmxLength);
    for (let i = 0; i < dmxLength; i++) {
      data[i] = msg[dmxStart + i] / 255.0;
    }

    this._latestData = data;
  }

  override async pull(tick: ITickContext): Promise<void> {
    // Output the latest received data, or zeros if no data yet
    let outData: Float32Array;
    if (this._latestData !== null) {
      outData = this._latestData;
    } else {
      // No data received yet - output zeros
      outData = new Float32Array(512);
    }

    const outPayload = new MatrixPayload(outData, 1);
    const outFrame = new Frame({
      topic: this._topic,
      timestamp: tick.wallTime,
      payload: outPayload,
      metadata: this._metadata,
    });

    this.outputs.get('out')?.write(outFrame);
  }
}
