/**
 * E1.31 (sACN) sink implementation.
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
 * E1.31 sink configuration.
 */
export interface IE131SinkConfig {
  id: string;
  universe: number;
  priority?: number;
  fps?: number;
  multicast?: boolean;
  destinationIp?: string;
}

/**
 * E1.31 packet header structure.
 */
export interface IE131PacketHeader {
  universe: number;
  priority: number;
  sequenceNumber: number;
  channelCount: number;
}

@node('E131Sink', 'sACN')
export class E131Sink extends BaseNode {
  readonly inputs = PortGroup.inputs({
    in: new InputPortSpec({ accepts: 'matrix' }),
  });

  private readonly _universe: number;
  private readonly _priority: number;
  private readonly _fps: number;
  readonly multicast: boolean;
  readonly destinationIp: string;
  private _sequenceNumber = 0;

  constructor(config: IE131SinkConfig) {
    super(config);
    this._universe = config.universe;
    this._priority = config.priority ?? 100;
    this._fps = config.fps ?? 44;
    this.multicast = config.multicast ?? true;
    this.destinationIp = config.destinationIp ?? this._getMulticastAddress();
  }

  override async start(ctx: NodeContext): Promise<void> {
    ctx.logger.info(
      `E131Sink '${this.id}' started: universe=${this._universe}, ` +
      `priority=${this._priority}, fps=${this._fps}`
    );
  }

  @pullRate(44)
  override async pull(tick: ITickContext): Promise<void> {
    const inPort = this.inputs.get('in');
    const frame = inPort ? (inPort as unknown as { read: () => Frame | null }).read() : null;
    if (!frame) return;

    const payload = frame.payload as MatrixPayload;
    const data = payload.flatten();

    // Convert to DMX values (0-255)
    const dmxData = new Uint8Array(Math.min(data.length, 512));
    for (let i = 0; i < dmxData.length; i++) {
      dmxData[i] = Math.round(Math.max(0, Math.min(1, data[i])) * 255);
    }

    // TODO: Send E1.31 packet via UDP
    this._sequenceNumber = (this._sequenceNumber + 1) % 256;

    void tick; // Suppress unused warning
  }

  private _getMulticastAddress(): string {
    return `239.255.${Math.floor(this._universe / 256)}.${this._universe % 256}`;
  }
}
