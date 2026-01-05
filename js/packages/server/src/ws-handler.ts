/**
 * WebSocket handler for RASL server.
 *
 * Provides real-time metrics streaming via WebSocket connections.
 */

import { WebSocketServer, WebSocket } from 'ws';
import type { Server } from 'node:http';
import type { UnifiedScheduler, INodeStats } from '@rasl/engine';
import type {
  IWsMessage,
  ISubscribeMessage,
  IUnsubscribeMessage,
  IErrorMessage,
} from './websocket.js';

/**
 * Metrics snapshot message.
 */
export interface IMetricsMessage extends IWsMessage {
  type: 'metrics';
  timestamp: number;
  nodes: Record<string, INodeStats>;
}

/**
 * WebSocket handler configuration.
 */
export interface IWsHandlerConfig {
  /** Minimum interval between metrics broadcasts (ms) */
  minIntervalMs?: number;
}

/**
 * Client subscription state.
 */
interface IClientState {
  subscriptions: Set<string>;
  metricsIntervalMs: number;
}

/**
 * WebSocket handler for real-time metrics streaming.
 */
export class WsHandler {
  private _wss: WebSocketServer | null = null;
  private _scheduler: UnifiedScheduler | null = null;
  private _clients = new Map<WebSocket, IClientState>();
  private _metricsTimer: ReturnType<typeof setInterval> | null = null;
  private readonly _minIntervalMs: number;

  constructor(config: IWsHandlerConfig = {}) {
    this._minIntervalMs = config.minIntervalMs ?? 50;
  }

  /**
   * Attach WebSocket server to HTTP server.
   */
  attach(httpServer: Server, scheduler: UnifiedScheduler): void {
    this._scheduler = scheduler;
    this._wss = new WebSocketServer({ server: httpServer });

    this._wss.on('connection', (ws) => this._handleConnection(ws));
  }

  /**
   * Detach and close WebSocket server.
   */
  detach(): void {
    if (this._metricsTimer) {
      clearInterval(this._metricsTimer);
      this._metricsTimer = null;
    }

    for (const ws of this._clients.keys()) {
      ws.close();
    }
    this._clients.clear();

    if (this._wss) {
      this._wss.close();
      this._wss = null;
    }

    this._scheduler = null;
  }

  /**
   * Handle new WebSocket connection.
   */
  private _handleConnection(ws: WebSocket): void {
    const state: IClientState = {
      subscriptions: new Set(),
      metricsIntervalMs: 1000,
    };
    this._clients.set(ws, state);

    ws.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString()) as IWsMessage;
        this._handleMessage(ws, state, msg);
      } catch {
        this._sendError(ws, 'Invalid JSON message');
      }
    });

    ws.on('close', () => {
      this._clients.delete(ws);
      this._updateMetricsTimer();
    });

    ws.on('error', () => {
      this._clients.delete(ws);
    });
  }

  /**
   * Handle incoming WebSocket message.
   */
  private _handleMessage(ws: WebSocket, state: IClientState, msg: IWsMessage): void {
    switch (msg.type) {
      case 'subscribe':
        this._handleSubscribe(ws, state, msg as ISubscribeMessage);
        break;
      case 'unsubscribe':
        this._handleUnsubscribe(state, msg as IUnsubscribeMessage);
        break;
      default:
        this._sendError(ws, `Unknown message type: ${msg.type}`);
    }
  }

  /**
   * Handle subscribe message.
   */
  private _handleSubscribe(ws: WebSocket, state: IClientState, msg: ISubscribeMessage): void {
    const topic = msg.topic;

    if (topic === 'metrics') {
      state.subscriptions.add('metrics');
      // Allow custom interval via payload
      const intervalMs = (msg.payload as { intervalMs?: number })?.intervalMs;
      if (typeof intervalMs === 'number' && intervalMs >= this._minIntervalMs) {
        state.metricsIntervalMs = intervalMs;
      }
      this._updateMetricsTimer();

      // Send immediate metrics snapshot
      this._sendMetrics(ws);
    } else {
      this._sendError(ws, `Unknown topic: ${topic}`);
    }
  }

  /**
   * Handle unsubscribe message.
   */
  private _handleUnsubscribe(state: IClientState, msg: IUnsubscribeMessage): void {
    state.subscriptions.delete(msg.topic);
    this._updateMetricsTimer();
  }

  /**
   * Update metrics broadcast timer based on subscriptions.
   */
  private _updateMetricsTimer(): void {
    // Find minimum interval among all metrics subscribers
    let minInterval = Infinity;
    let hasSubscribers = false;

    for (const [, state] of this._clients) {
      if (state.subscriptions.has('metrics')) {
        hasSubscribers = true;
        minInterval = Math.min(minInterval, state.metricsIntervalMs);
      }
    }

    // Clear existing timer
    if (this._metricsTimer) {
      clearInterval(this._metricsTimer);
      this._metricsTimer = null;
    }

    // Start new timer if we have subscribers
    if (hasSubscribers && minInterval < Infinity) {
      const interval = Math.max(minInterval, this._minIntervalMs);
      this._metricsTimer = setInterval(() => this._broadcastMetrics(), interval);
    }
  }

  /**
   * Broadcast metrics to all subscribed clients.
   */
  private _broadcastMetrics(): void {
    for (const [ws, state] of this._clients) {
      if (state.subscriptions.has('metrics') && ws.readyState === WebSocket.OPEN) {
        this._sendMetrics(ws);
      }
    }
  }

  /**
   * Send metrics snapshot to a client.
   */
  private _sendMetrics(ws: WebSocket): void {
    if (!this._scheduler || ws.readyState !== WebSocket.OPEN) return;

    const allStats = this._scheduler.getNodeStats() as Map<string, INodeStats> | null;
    const nodes: Record<string, INodeStats> = {};
    if (allStats) {
      for (const [id, stats] of allStats) {
        nodes[id] = stats;
      }
    }

    const msg: IMetricsMessage = {
      type: 'metrics',
      timestamp: Date.now(),
      nodes,
    };

    ws.send(JSON.stringify(msg));
  }

  /**
   * Send error message to client.
   */
  private _sendError(ws: WebSocket, message: string): void {
    if (ws.readyState !== WebSocket.OPEN) return;

    const msg: IErrorMessage = {
      type: 'error',
      message,
    };

    ws.send(JSON.stringify(msg));
  }
}
