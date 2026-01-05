/**
 * WebSocket client for connecting to RASL server.
 */

import { ErrorCodes, RaslError } from "@rasl/engine";

/**
 * WebSocket client configuration.
 */
export interface IWebSocketClientConfig {
  url: string;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

/**
 * WebSocket message handler.
 */
export type MessageHandler = (data: unknown) => void;

/**
 * WebSocket client for RASL server communication.
 */
export class WebSocketClient {
  private readonly _config: Required<IWebSocketClientConfig>;
  private _ws: WebSocket | null = null;
  private _reconnectAttempts = 0;
  private _handlers = new Map<string, Set<MessageHandler>>();
  private _connected = false;

  constructor(config: IWebSocketClientConfig) {
    this._config = {
      url: config.url,
      reconnectInterval: config.reconnectInterval ?? 1000,
      maxReconnectAttempts: config.maxReconnectAttempts ?? 10,
    };
  }

  /**
   * Connect to the WebSocket server.
   */
  connect(): void {
    if (this._ws) {
      this._ws.close();
    }

    this._ws = new WebSocket(this._config.url);

    this._ws.onopen = () => {
      this._connected = true;
      this._reconnectAttempts = 0;
      this._emit("connected", null);
    };

    this._ws.onclose = () => {
      this._connected = false;
      this._emit("disconnected", null);
      this._attemptReconnect();
    };

    this._ws.onerror = (error) => {
      this._emit("error", error);
    };

    this._ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data as string);
        const type = data.type as string;
        this._emit(type, data);
        this._emit("message", data);
      } catch {
        this._emit("error", new RaslError(ErrorCodes.ParseError, "Failed to parse message"));
      }
    };
  }

  /**
   * Disconnect from the server.
   */
  disconnect(): void {
    if (this._ws) {
      this._ws.close();
      this._ws = null;
    }
    this._connected = false;
  }

  /**
   * Subscribe to a topic.
   */
  subscribe(topic: string): void {
    this._send({ type: "subscribe", topic });
  }

  /**
   * Unsubscribe from a topic.
   */
  unsubscribe(topic: string): void {
    this._send({ type: "unsubscribe", topic });
  }

  /**
   * Add an event handler.
   */
  on(event: string, handler: MessageHandler): void {
    if (!this._handlers.has(event)) {
      this._handlers.set(event, new Set());
    }
    this._handlers.get(event)!.add(handler);
  }

  /**
   * Remove an event handler.
   */
  off(event: string, handler: MessageHandler): void {
    this._handlers.get(event)?.delete(handler);
  }

  /**
   * Check if connected.
   */
  get isConnected(): boolean {
    return this._connected;
  }

  private _send(data: unknown): void {
    if (this._ws && this._connected) {
      this._ws.send(JSON.stringify(data));
    }
  }

  private _emit(event: string, data: unknown): void {
    const handlers = this._handlers.get(event);
    if (handlers) {
      for (const handler of handlers) {
        handler(data);
      }
    }
  }

  private _attemptReconnect(): void {
    if (this._reconnectAttempts >= this._config.maxReconnectAttempts) {
      this._emit("reconnect_failed", null);
      return;
    }

    this._reconnectAttempts++;
    setTimeout(() => {
      this.connect();
    }, this._config.reconnectInterval);
  }
}
