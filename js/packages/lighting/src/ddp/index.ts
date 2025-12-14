/**
 * DDP (Distributed Display Protocol) sink implementation.
 */

import {
  BaseNode,
  Frame,
  MatrixPayload,
  PortGroup,
  InputPortSpec,
  type ITickContext,
  type NodeContext,
  node,
  pullRate,
} from '@rasl/engine';

/**
 * DDP sink configuration.
 */
export interface IDdpSinkConfig {
  id: string;
  host: string;
  port?: number;
  fps?: number;
  offset?: number;
}

/**
 * DDP packet flags.
 */
export const DdpFlags = {
  Version1: 0xc1,
  Push: 0x01,
  Query: 0x02,
  Reply: 0x04,
  Storage: 0x08,
  Timecode: 0x10,
} as const;
export type DdpFlags = (typeof DdpFlags)[keyof typeof DdpFlags];

/**
 * DDP packet header structure.
 */
export interface IDdpPacketHeader {
  flags: number;
  sequenceNumber: number;
  dataType: number;
  offset: number;
  length: number;
}

@node('DdpSink', 'DDP')
export class DdpSink extends BaseNode {
  readonly inputs = PortGroup.inputs({
    in: new InputPortSpec({ accepts: 'matrix' }),
  });

  private readonly _host: string;
  private readonly _port: number;
  private readonly _fps: number;
  private readonly _offset: number;
  private _sequenceNumber = 0;

  constructor(config: IDdpSinkConfig) {
    super(config);
    this._host = config.host;
    this._port = config.port ?? 4048;
    this._fps = config.fps ?? 44;
    this._offset = config.offset ?? 0;
  }

  override async start(ctx: NodeContext): Promise<void> {
    ctx.logger.info(
      `DdpSink '${this.id}' started: host=${this._host}:${this._port}, fps=${this._fps}`
    );
  }

  @pullRate(44)
  override async pull(tick: ITickContext): Promise<void> {
    const inPort = this.inputs.get('in');
    const frame = inPort ? (inPort as unknown as { read: () => Frame | null }).read() : null;
    if (!frame) return;

    const payload = frame.payload as MatrixPayload;
    const data = payload.flatten();

    // Convert to RGB bytes (0-255)
    const rgbData = new Uint8Array(data.length);
    for (let i = 0; i < data.length; i++) {
      rgbData[i] = Math.round(Math.max(0, Math.min(1, data[i])) * 255);
    }

    // TODO: Send DDP packet via UDP
    this._sequenceNumber = (this._sequenceNumber + 1) % 16;

    void tick; // Suppress unused warning
  }

  /**
   * Build a DDP packet header.
   */
  buildHeader(dataLength: number): IDdpPacketHeader {
    return {
      flags: DdpFlags.Version1 | DdpFlags.Push,
      sequenceNumber: this._sequenceNumber,
      dataType: 0x01, // RGB
      offset: this._offset,
      length: dataLength,
    };
  }
}
