/**
 * LIFX LAN protocol client.
 */

import * as dgram from 'node:dgram';

export const LIFX_DEFAULT_PORT = 56700;
const LIGHT_SET_COLOR = 102;
const PROTOCOL_NUMBER = 0x400;

const UINT16_MAX = 0xFFFF;
const MIN_KELVIN = 1500;
const MAX_KELVIN = 9000;
const KELVIN_RANGE = MAX_KELVIN - MIN_KELVIN;

export interface ILifxEndpoint {
  ip: string;
  port: number;
  mac?: Uint8Array;
}

export interface ILifxLanClientOptions {
  sourceId?: number;
}

/**
 * Minimal LIFX LAN sender that targets a single endpoint.
 */
export class LifxLanClient {
  private readonly _endpoint: ILifxEndpoint;
  private readonly _sourceId: number;
  private _sequence = 0;
  private _socket: dgram.Socket | null = null;

  constructor(endpoint: ILifxEndpoint, options: ILifxLanClientOptions = {}) {
    this._endpoint = endpoint;
    this._sourceId = options.sourceId ?? Math.floor(Math.random() * 0xFFFFFFFF);
  }

  get endpoint(): ILifxEndpoint {
    return this._endpoint;
  }

  async start(): Promise<void> {
    return new Promise((resolve, reject) => {
      const socket = dgram.createSocket('udp4');
      
      socket.on('error', (err) => {
        this._socket = null;
        reject(err);
      });

      socket.connect(this._endpoint.port, this._endpoint.ip, () => {
        this._socket = socket;
        resolve();
      });
    });
  }

  stop(): void {
    if (this._socket !== null) {
      this._socket.close();
      this._socket = null;
    }
  }

  describe(): { ip: string; port: number; mac: string | null } {
    return {
      ip: this._endpoint.ip,
      port: this._endpoint.port,
      mac: this._endpoint.mac ? Buffer.from(this._endpoint.mac).toString('hex') : null,
    };
  }

  sendSetColor(
    hue: number,
    saturation: number,
    brightness: number,
    kelvin: number,
    durationMs: number,
    rapid: boolean
  ): void {
    if (this._socket === null) {
      throw new Error('LifxLanClient has not been started');
    }

    const packet = encodeSetColorPacket({
      sourceId: this._sourceId,
      sequence: this._sequence,
      mac: this._endpoint.mac ?? null,
      hue,
      saturation,
      brightness,
      kelvin,
      durationMs: Math.max(0, Math.floor(durationMs)),
      rapid,
    });

    this._sequence = (this._sequence + 1) % 256;
    this._socket.send(packet);
  }
}

/**
 * Parse comma-separated target specs into endpoints.
 */
export function parseTargetList(value: string): ILifxEndpoint[] {
  const specs = value.split(',').map((s) => s.trim()).filter(Boolean);
  return specs.map(parseSingleTarget);
}

function parseSingleTarget(spec: string): ILifxEndpoint {
  let mac: Uint8Array | undefined;
  let target = spec;

  if (spec.includes('@')) {
    const [macText, rest] = spec.split('@', 2);
    mac = parseMac(macText.trim());
    target = rest;
  }

  const { host, port } = parseHostPort(target.trim());
  return { ip: host, port, mac };
}

function parseMac(value: string): Uint8Array {
  const cleaned = value.replace(/[:-]/g, '');
  if (cleaned.length !== 12 && cleaned.length !== 16) {
    throw new Error(`invalid MAC '${value}'`);
  }

  const bytes: number[] = [];
  for (let i = 0; i < cleaned.length; i += 2) {
    bytes.push(parseInt(cleaned.slice(i, i + 2), 16));
  }

  // Return first 6 bytes (standard MAC)
  return new Uint8Array(bytes.slice(0, 6));
}

function parseHostPort(target: string): { host: string; port: number } {
  if (!target) {
    throw new Error('target host cannot be empty');
  }

  // IPv6 literal
  if (target.startsWith('[')) {
    const end = target.indexOf(']');
    if (end === -1) {
      throw new Error(`invalid IPv6 target '${target}'`);
    }
    const host = target.slice(1, end);
    let port = LIFX_DEFAULT_PORT;
    const remainder = target.slice(end + 1);
    if (remainder) {
      if (!remainder.startsWith(':')) {
        throw new Error(`invalid IPv6 target '${target}'`);
      }
      port = parseInt(remainder.slice(1), 10);
    }
    return { host, port };
  }

  // IPv4 with optional port
  if (target.includes(':') && target.split(':').length === 2) {
    const [host, portText] = target.split(':');
    if (!host) {
      throw new Error(`invalid host in target '${target}'`);
    }
    return { host, port: parseInt(portText, 10) };
  }

  return { host: target, port: LIFX_DEFAULT_PORT };
}

interface ISetColorPacketParams {
  sourceId: number;
  sequence: number;
  mac: Uint8Array | null;
  hue: number;
  saturation: number;
  brightness: number;
  kelvin: number;
  durationMs: number;
  rapid: boolean;
}

function encodeSetColorPacket(params: ISetColorPacketParams): Buffer {
  const { sourceId, sequence, mac, hue, saturation, brightness, kelvin, durationMs } = params;

  const tagged = mac ? 0 : 1;
  const frameFlags = buildFrameFlags(tagged);
  const target = encodeTarget(mac);

  // Frame header (8 bytes)
  const frameHeader = Buffer.alloc(8);
  const size = 49; // Total packet size for SetColor
  frameHeader.writeUInt16LE(size, 0);
  frameHeader.writeUInt16LE(frameFlags, 2);
  frameHeader.writeUInt32LE(sourceId >>> 0, 4);

  // Frame address (16 bytes)
  const frameAddress = Buffer.alloc(16);
  target.copy(frameAddress, 0);
  // 6 bytes reserved (already zero)
  frameAddress.writeUInt8(0, 14); // res_required | ack_required
  frameAddress.writeUInt8(sequence & 0xFF, 15);

  // Protocol header (12 bytes)
  const protocolHeader = Buffer.alloc(12);
  // 8 bytes reserved (already zero)
  protocolHeader.writeUInt16LE(LIGHT_SET_COLOR, 8);
  // 2 bytes reserved (already zero)

  // Payload (13 bytes)
  const payload = Buffer.alloc(13);
  payload.writeUInt8(0, 0); // reserved
  payload.writeUInt16LE(hue & 0xFFFF, 1);
  payload.writeUInt16LE(saturation & 0xFFFF, 3);
  payload.writeUInt16LE(brightness & 0xFFFF, 5);
  payload.writeUInt16LE(kelvin & 0xFFFF, 7);
  payload.writeUInt32LE(durationMs >>> 0, 9);

  return Buffer.concat([frameHeader, frameAddress, protocolHeader, payload]);
}

function buildFrameFlags(tagged: number): number {
  const origin = 0;
  const addressable = 1;
  let value = PROTOCOL_NUMBER & 0x0FFF;
  value |= (addressable & 0x1) << 12;
  value |= (tagged & 0x1) << 13;
  value |= (origin & 0x3) << 14;
  return value;
}

function encodeTarget(mac: Uint8Array | null): Buffer {
  const target = Buffer.alloc(8);
  if (mac !== null && mac.length >= 6) {
    target.set(mac.slice(0, 6), 0);
  }
  return target;
}

/**
 * Convert HSBK float values [0,1] to LIFX protocol integers.
 */
export function hsbkToLifx(
  h: number,
  s: number,
  b: number,
  k: number
): { hue: number; saturation: number; brightness: number; kelvin: number } {
  const hue = Math.round(Math.max(0, Math.min(1, h)) * UINT16_MAX) % (UINT16_MAX + 1);
  const saturation = Math.round(Math.max(0, Math.min(1, s)) * UINT16_MAX);
  const brightness = Math.round(Math.max(0, Math.min(1, b)) * UINT16_MAX);
  const kelvinRaw = Math.round(Math.max(0, Math.min(1, k)) * KELVIN_RANGE + MIN_KELVIN);
  const kelvin = Math.max(MIN_KELVIN, Math.min(MAX_KELVIN, kelvinRaw));
  return { hue, saturation, brightness, kelvin };
}
