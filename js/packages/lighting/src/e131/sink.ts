/**
 * SacnSink - Transmits DMX data via sACN/E1.31 protocol.
 *
 * Sends DMX channel data as sACN packets to network devices.
 */

import * as dgram from "node:dgram";

import type {
  InputPort,
  MatrixPayload} from "@rasl/engine";
import {
  BaseNode,
  InputPortSpec,
  type ITickContext,
  node,
  type NodeContext,
  PortGroup,
  pullRate,
} from "@rasl/engine";

export interface ISacnSinkConfig {
  id: string;
  targetHost?: string;
  targetUniverse?: number;
  fps?: number;
  sourceName?: string;
  priority?: number;
  inputPort?: string;
}

const SACN_PORT = 5568;

// sACN E1.31 packet structure
function buildSacnPacket(
  universe: number,
  dmxData: Uint8Array,
  sequence: number,
  sourceName: string,
  priority: number,
): Buffer {
  // Full sACN packet is 638 bytes for 512 DMX channels
  const packet = Buffer.alloc(638);
  let offset = 0;

  // Root Layer (38 bytes)
  // Preamble Size (2 bytes)
  packet.writeUInt16BE(0x0010, offset);
  offset += 2;
  // Post-amble Size (2 bytes)
  packet.writeUInt16BE(0x0000, offset);
  offset += 2;
  // ACN Packet Identifier (12 bytes)
  packet.write("ASC-E1.17\0\0\0", offset, "ascii");
  offset += 12;
  // Flags and Length (2 bytes) - 0x7000 | (packet length - 16)
  packet.writeUInt16BE(0x7000 | (638 - 16), offset);
  offset += 2;
  // Vector (4 bytes) - VECTOR_ROOT_E131_DATA
  packet.writeUInt32BE(0x00000004, offset);
  offset += 4;
  // CID (16 bytes) - unique identifier
  for (let i = 0; i < 16; i++) {
    packet.writeUInt8(i, offset + i);
  }
  offset += 16;

  // Framing Layer (77 bytes)
  // Flags and Length (2 bytes)
  packet.writeUInt16BE(0x7000 | (638 - 38), offset);
  offset += 2;
  // Vector (4 bytes) - VECTOR_E131_DATA_PACKET
  packet.writeUInt32BE(0x00000002, offset);
  offset += 4;
  // Source Name (64 bytes)
  const nameBytes = Buffer.alloc(64);
  nameBytes.write(sourceName.slice(0, 63), 0, "utf8");
  nameBytes.copy(packet, offset);
  offset += 64;
  // Priority (1 byte)
  packet.writeUInt8(priority, offset);
  offset += 1;
  // Synchronization Address (2 bytes)
  packet.writeUInt16BE(0, offset);
  offset += 2;
  // Sequence Number (1 byte)
  packet.writeUInt8(sequence & 0xff, offset);
  offset += 1;
  // Options (1 byte)
  packet.writeUInt8(0, offset);
  offset += 1;
  // Universe (2 bytes)
  packet.writeUInt16BE(universe, offset);
  offset += 2;

  // DMP Layer (523 bytes)
  // Flags and Length (2 bytes)
  packet.writeUInt16BE(0x7000 | (638 - 115), offset);
  offset += 2;
  // Vector (1 byte) - VECTOR_DMP_SET_PROPERTY
  packet.writeUInt8(0x02, offset);
  offset += 1;
  // Address Type & Data Type (1 byte)
  packet.writeUInt8(0xa1, offset);
  offset += 1;
  // First Property Address (2 bytes)
  packet.writeUInt16BE(0, offset);
  offset += 2;
  // Address Increment (2 bytes)
  packet.writeUInt16BE(1, offset);
  offset += 2;
  // Property value count (2 bytes) - 513 (start code + 512 channels)
  packet.writeUInt16BE(513, offset);
  offset += 2;
  // Start Code (1 byte)
  packet.writeUInt8(0, offset);
  offset += 1;
  // DMX Data (512 bytes)
  for (let i = 0; i < 512; i++) {
    packet.writeUInt8(dmxData[i] ?? 0, offset + i);
  }

  return packet;
}

@node("SacnSinkNode", "SacnSink")
export class SacnSinkNode extends BaseNode {
  readonly inputs: PortGroup<InputPort>;

  private readonly _targetHost: string;
  private readonly _targetUniverse: number;
  private readonly _fps: number;
  private readonly _sourceName: string;
  private readonly _priority: number;
  private readonly _inputPort: string;
  private _socket: dgram.Socket | null = null;
  private _sequence = 0;

  constructor(config: ISacnSinkConfig) {
    super(config);
    this._targetHost = config.targetHost ?? "255.255.255.255";
    this._targetUniverse = config.targetUniverse ?? 1;
    this._fps = config.fps ?? 40;
    this._sourceName = config.sourceName ?? "RASL";
    this._priority = config.priority ?? 100;
    this._inputPort = config.inputPort ?? "dmx";

    this.inputs = PortGroup.inputs({
      [this._inputPort]: new InputPortSpec({ accepts: ["matrix", "color"] }),
    });
  }

  override async start(ctx: NodeContext): Promise<void> {
    this._socket = dgram.createSocket("udp4");
    this._socket.on("error", (err) => {
      ctx.logger.error(`SacnSink '${this.id}' error: ${err.message}`);
    });
    ctx.logger.info(
      `SacnSink '${this.id}' sending to ${this._targetHost}:${SACN_PORT} universe ${this._targetUniverse} at ${this._fps} FPS`,
    );
  }

  override async stop(ctx: NodeContext): Promise<void> {
    if (this._socket !== null) {
      this._socket.close();
      this._socket = null;
    }
    ctx.logger.info(`SacnSink '${this.id}' stopped`);
  }

  @pullRate((self: unknown) => (self as SacnSinkNode)._fps)
  override async pull(tick: ITickContext): Promise<void> {
    if (this._socket === null) return;

    const inPort = this.inputs.get(this._inputPort);
    const frame = inPort?.read() ?? null;
    if (!frame) return;

    const payload = frame.payload as MatrixPayload;
    const data = payload.flatten();

    // Convert float [0,1] to uint8 [0,255]
    const dmxData = new Uint8Array(512);
    for (let i = 0; i < Math.min(data.length, 512); i++) {
      dmxData[i] = Math.round(Math.max(0, Math.min(1, data[i])) * 255);
    }

    // Build and send packet
    this._sequence = (this._sequence + 1) & 0xff;
    const packet = buildSacnPacket(this._targetUniverse, dmxData, this._sequence, this._sourceName, this._priority);

    this._socket.send(packet, SACN_PORT, this._targetHost);

    void tick;
  }
}
