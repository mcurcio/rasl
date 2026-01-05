/**
 * DDP (Distributed Display Protocol) client implementation.
 *
 * Sends RGB pixel data to LED controllers over UDP.
 * DDP is optimized for high pixel counts with up to 480 RGB pixels per packet.
 *
 * Protocol reference: http://www.3waylabs.com/ddp/
 */

import * as dgram from "node:dgram";

import { ErrorCodes, RaslError } from "@rasl/engine";

export const DDP_PORT = 4048;
export const DDP_HEADER_LEN = 10;
export const DDP_MAX_DATALEN = 1440; // 480 RGB pixels

// Flags
export const DDP_VER1 = 0x40;
export const DDP_PUSH = 0x01;
export const DDP_DATATYPE_RGB = 0x00;
export const DDP_DEFAULT_DEST_ID = 0x01;

export class DDPClient {
  private readonly _host: string;
  private readonly _port: number;
  private readonly _destinationId: number;
  private _socket: dgram.Socket | null = null;
  private _sequence = 0;

  constructor(host: string, port: number = DDP_PORT, destinationId: number = DDP_DEFAULT_DEST_ID) {
    this._host = host;
    this._port = port;
    this._destinationId = destinationId;
  }

  connect(): void {
    if (this._socket === null) {
      this._socket = dgram.createSocket("udp4");
    }
  }

  close(): void {
    if (this._socket !== null) {
      this._socket.close();
      this._socket = null;
    }
  }

  /**
   * Send pixel data as DDP packets.
   * Data should be Uint8Array of RGB values (0-255).
   */
  send(data: Uint8Array): void {
    if (this._socket === null) {
      throw new RaslError(ErrorCodes.NotReady, "DDPClient not connected. Call connect() first.");
    }

    const totalLen = data.length;
    if (totalLen === 0) return;

    const numPackets = Math.ceil(totalLen / DDP_MAX_DATALEN);

    for (let i = 0; i < numPackets; i++) {
      const byteOffset = i * DDP_MAX_DATALEN;
      const chunk = data.subarray(byteOffset, byteOffset + DDP_MAX_DATALEN);
      const isLast = i === numPackets - 1;
      this._sequence = (this._sequence % 15) + 1;

      this._sendPacket(this._sequence, byteOffset, chunk, isLast);
    }
  }

  /**
   * Send as many packets as possible.
   * Returns the next byte offset to resume from. Returns 0 when complete.
   */
  sendNonblocking(data: Uint8Array, startOffset: number = 0, pushEveryPacket: boolean = false): number {
    if (this._socket === null) {
      throw new RaslError(ErrorCodes.NotReady, "DDPClient not connected. Call connect() first.");
    }

    const totalLen = data.length;
    if (totalLen === 0) return 0;

    let offset = Math.max(0, startOffset);
    if (offset >= totalLen) return 0;

    while (offset < totalLen) {
      const chunk = data.subarray(offset, offset + DDP_MAX_DATALEN);
      const isLast = offset + chunk.length >= totalLen;
      this._sequence = (this._sequence % 15) + 1;

      this._sendPacket(this._sequence, offset, chunk, isLast, pushEveryPacket);
      offset += chunk.length;
    }

    return 0;
  }

  private _sendPacket(
    sequence: number,
    byteOffset: number,
    data: Uint8Array,
    isLast: boolean,
    pushEveryPacket: boolean = false,
  ): void {
    if (this._socket === null) return;

    const flags = DDP_VER1 | (pushEveryPacket || isLast ? DDP_PUSH : 0);
    const dataLen = data.length;

    // Build header (10 bytes)
    const header = Buffer.alloc(DDP_HEADER_LEN);
    header.writeUInt8(flags, 0);
    header.writeUInt8(sequence & 0x0f, 1);
    header.writeUInt8(DDP_DATATYPE_RGB, 2);
    header.writeUInt8(this._destinationId, 3);
    header.writeUInt32BE(byteOffset, 4);
    header.writeUInt16BE(dataLen, 8);

    // Combine header and data
    const packet = Buffer.concat([header, Buffer.from(data)]);

    // Send via UDP
    this._socket.send(packet, this._port, this._host);
  }
}
