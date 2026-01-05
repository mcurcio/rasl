/**
 * TCP client utilities for the Govee LAN API.
 */

import * as net from "node:net";

import { ErrorCodes, RaslError } from "@rasl/engine";

export const DEFAULT_GOVEE_PORT = 4003;
export const DEFAULT_CONNECT_TIMEOUT = 2000;
export const DEFAULT_READ_TIMEOUT = 2000;
export const DEFAULT_BASE_BACKOFF = 500;
export const DEFAULT_MAX_BACKOFF = 8000;

export interface IGoveeSegmentInfo {
  segmentId: number;
  length?: number;
}

export interface IGoveeDeviceInfo {
  segments: IGoveeSegmentInfo[];
  channelsPerSegment: number;
  supportsWhiteChannel: boolean;
  raw: Record<string, unknown>;
}

export interface IGoveeColor {
  r: number;
  g: number;
  b: number;
  w?: number;
}

export interface IGoveeSegmentColor extends IGoveeColor {
  segmentId: number;
}

export interface IGoveeLightClientOptions {
  connectTimeout?: number;
  readTimeout?: number;
  baseBackoff?: number;
  maxBackoff?: number;
  timeFn?: () => number;
}

/**
 * Minimal TCP client for the Govee LAN JSON protocol.
 */
export class GoveeLightClient {
  readonly host: string;
  readonly port: number;

  private readonly _connectTimeout: number;
  private readonly _readTimeout: number;
  private readonly _baseBackoff: number;
  private readonly _maxBackoff: number;
  private readonly _timeFn: () => number;

  private _socket: net.Socket | null = null;
  private _recvBuffer: Buffer = Buffer.alloc(0);
  private _nextRetryAt = 0;
  private _backoff: number;
  private _lastError: Error | null = null;
  private _connected = false;
  private _pendingResolve: ((value: Record<string, unknown>) => void) | null = null;
  private _pendingReject: ((reason: Error) => void) | null = null;

  constructor(host: string, port = DEFAULT_GOVEE_PORT, options: IGoveeLightClientOptions = {}) {
    this.host = host;
    this.port = port;
    this._connectTimeout = Math.max(100, options.connectTimeout ?? DEFAULT_CONNECT_TIMEOUT);
    this._readTimeout = Math.max(100, options.readTimeout ?? DEFAULT_READ_TIMEOUT);
    this._baseBackoff = Math.max(100, options.baseBackoff ?? DEFAULT_BASE_BACKOFF);
    this._maxBackoff = Math.max(this._baseBackoff, options.maxBackoff ?? DEFAULT_MAX_BACKOFF);
    this._timeFn = options.timeFn ?? (() => Date.now());
    this._backoff = this._baseBackoff;
  }

  get lastError(): Error | null {
    return this._lastError;
  }

  get isConnected(): boolean {
    return this._connected && this._socket !== null;
  }

  close(): void {
    if (this._socket !== null) {
      try {
        this._socket.destroy();
      } finally {
        this._socket = null;
        this._connected = false;
        this._recvBuffer = Buffer.alloc(0);
      }
    }
  }

  /**
   * Emit a `colorwc` command to set segment colors.
   */
  sendColorCommand(color: IGoveeColor | null, segments?: IGoveeSegmentColor[]): void {
    const data: Record<string, unknown> = {};
    if (color) {
      data.color = color;
    }
    if (segments && segments.length > 0) {
      data.segments = segments;
    }
    if (Object.keys(data).length === 0) {
      throw new RaslError(ErrorCodes.InvalidArgument, "color or segments must be provided");
    }

    const payload = { msg: { cmd: "colorwc", data } };
    this._sendCommand(payload, false);
  }

  /**
   * Send `devStatus` and return the parsed response.
   */
  async queryStatus(): Promise<Record<string, unknown>> {
    const payload = { msg: { cmd: "devStatus", data: {} } };
    return this._sendCommand(payload, true) ?? {};
  }

  /**
   * Run `devStatus` and interpret core metadata.
   */
  async discover(): Promise<IGoveeDeviceInfo | null> {
    const reply = await this.queryStatus();
    if (!reply || Object.keys(reply).length === 0) {
      return null;
    }

    const data = extractMsgData(reply);
    const segments = parseSegments(data);
    const channels = inferChannels(data, segments);

    return {
      segments,
      channelsPerSegment: channels,
      supportsWhiteChannel: channels === 4,
      raw: data,
    };
  }

  private _sendCommand(
    payload: Record<string, unknown>,
    expectReply: boolean,
  ): Promise<Record<string, unknown>> | null {
    const message = JSON.stringify(payload) + "\n";
    const data = Buffer.from(message, "utf-8");

    const socket = this._ensureConnection();
    if (socket === null) {
      throw new RaslError(ErrorCodes.NetworkError, `unable to connect to ${this.host}:${this.port}`);
    }

    socket.write(data);

    if (!expectReply) {
      return null;
    }

    return this._readReply();
  }

  private _readReply(): Promise<Record<string, unknown>> {
    return new Promise((resolve, reject) => {
      this._pendingResolve = resolve;
      this._pendingReject = reject;

      const timeout = setTimeout(() => {
        this._pendingResolve = null;
        this._pendingReject = null;
        reject(new RaslError(ErrorCodes.TimedOut, "timed out waiting for Govee reply"));
      }, this._readTimeout);

      const checkBuffer = () => {
        const newlineIndex = this._recvBuffer.indexOf("\n");
        if (newlineIndex !== -1) {
          clearTimeout(timeout);
          const line = this._recvBuffer.subarray(0, newlineIndex).toString("utf-8").trim();
          this._recvBuffer = this._recvBuffer.subarray(newlineIndex + 1);
          this._pendingResolve = null;
          this._pendingReject = null;
          if (line) {
            try {
              resolve(JSON.parse(line));
            } catch {
              reject(new RaslError(ErrorCodes.ParseError, "invalid JSON response"));
            }
          } else {
            resolve({});
          }
        }
      };

      // Check if we already have data
      checkBuffer();

      // Set up data handler if not already resolved
      if (this._pendingResolve !== null && this._socket) {
        const onData = (chunk: Buffer) => {
          this._recvBuffer = Buffer.concat([this._recvBuffer, chunk]);
          checkBuffer();
        };
        this._socket.once("data", onData);
      }
    });
  }

  private _ensureConnection(): net.Socket | null {
    const now = this._timeFn();

    if (this._socket !== null && this._connected) {
      return this._socket;
    }

    if (now < this._nextRetryAt) {
      return null;
    }

    try {
      const socket = new net.Socket();
      socket.setTimeout(this._connectTimeout);

      socket.on("error", (err) => {
        this._recordFailure(err);
        if (this._pendingReject) {
          this._pendingReject(err);
          this._pendingResolve = null;
          this._pendingReject = null;
        }
      });

      socket.on("close", () => {
        this._connected = false;
        this._socket = null;
      });

      socket.on("data", (chunk) => {
        this._recvBuffer = Buffer.concat([this._recvBuffer, chunk]);
      });

      socket.connect(this.port, this.host, () => {
        this._connected = true;
        this._backoff = this._baseBackoff;
        this._lastError = null;
      });

      this._socket = socket;
      this._recvBuffer = Buffer.alloc(0);

      // Wait briefly for connection
      return socket;
    } catch (err) {
      this._recordFailure(err as Error);
      return null;
    }
  }

  private _recordFailure(err: Error): void {
    this.close();
    this._lastError = err;
    const now = this._timeFn();
    this._nextRetryAt = now + this._backoff;
    this._backoff = Math.min(this._backoff * 2, this._maxBackoff);
  }
}

function extractMsgData(response: Record<string, unknown>): Record<string, unknown> {
  let data = response;
  const msg = response.msg;
  if (msg && typeof msg === "object") {
    const msgObj = msg as Record<string, unknown>;
    data = (msgObj.data as Record<string, unknown>) ?? msgObj;
  }
  return typeof data === "object" && data !== null ? data : {};
}

function parseSegments(data: Record<string, unknown>): IGoveeSegmentInfo[] {
  let rawSegments: unknown[] | null = null;

  const icSegments = data.icSegments;
  if (icSegments && typeof icSegments === "object") {
    if (Array.isArray(icSegments)) {
      rawSegments = icSegments;
    } else {
      const icObj = icSegments as Record<string, unknown>;
      const segmentsObj = icObj.segments ?? icObj.icSegs;
      if (Array.isArray(segmentsObj)) {
        rawSegments = segmentsObj;
      }
    }
  }

  if (rawSegments === null) {
    const segmentsField = data.segments;
    if (Array.isArray(segmentsField)) {
      rawSegments = segmentsField;
    }
  }

  const segments: IGoveeSegmentInfo[] = [];
  if (rawSegments === null) {
    return segments;
  }

  for (let idx = 0; idx < rawSegments.length; idx++) {
    const seg = rawSegments[idx];
    if (!seg || typeof seg !== "object") {
      continue;
    }
    const segObj = seg as Record<string, unknown>;
    const segmentId = typeof segObj.segmentId === "number" ? segObj.segmentId : idx;
    const lengthVal = segObj.count ?? segObj.len ?? segObj.ledCount;
    const length = typeof lengthVal === "number" ? lengthVal : undefined;
    segments.push({ segmentId, length });
  }

  return segments;
}

function inferChannels(data: Record<string, unknown>, segments: IGoveeSegmentInfo[]): number {
  const color = data.color;
  if (color && typeof color === "object" && "w" in (color as object)) {
    return 4;
  }

  const channelHint = data.channelCount;
  if (typeof channelHint === "number") {
    if (channelHint >= 4) return 4;
    if (channelHint >= 3) return 3;
  }

  if (segments.length > 0 && segments[0].length !== undefined) {
    return 3;
  }

  return 3;
}
