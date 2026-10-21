/**
 * WebSocket handler for RASL server.
 *
 * Provides real-time metrics streaming via WebSocket connections.
 */

import type { Server } from "node:http";

import { isExternalWritableNode, type IEngine } from "@rasl/engine";
import { WebSocket, WebSocketServer } from "ws";

import type {
  IErrorMessage,
  IExternalAckMessage,
  IExternalUpdateMessage,
  ISubscribeMessage,
  IUnsubscribeMessage,
  IWsMessage,
} from "./websocket.js";

/**
 * Metrics snapshot message.
 */
export interface IMetricsMessage extends IWsMessage {
  type: "metrics";
  timestamp: number;
  engineStats: {
    totalGraphs: number;
    runningGraphs: number;
    totalNodes: number;
    uptimeMs: number;
  };
  graphs: Record<string, {
    nodeCount: number;
    currentFps: number;
    framesProcessed: number;
    avgFrameTimeMs: number;
  }>;
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
  private _engine: IEngine | null = null;
  private _clients = new Map<WebSocket, IClientState>();
  private _metricsTimer: ReturnType<typeof setInterval> | null = null;
  private readonly _minIntervalMs: number;

  constructor(config: IWsHandlerConfig = {}) {
    this._minIntervalMs = config.minIntervalMs ?? 50;
  }

  /**
   * Attach WebSocket server to HTTP server.
   */
  attach(httpServer: Server, engine: IEngine): void {
    this._engine = engine;
    this._wss = new WebSocketServer({ server: httpServer });

    this._wss.on("connection", (ws) => this._handleConnection(ws));
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

    this._engine = null;
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

    ws.on("message", (data) => {
      try {
        const msg = JSON.parse(data.toString()) as IWsMessage;
        this._handleMessage(ws, state, msg);
      } catch {
        this._sendError(ws, "Invalid JSON message");
      }
    });

    ws.on("close", () => {
      this._clients.delete(ws);
      this._updateMetricsTimer();
    });

    ws.on("error", () => {
      this._clients.delete(ws);
    });
  }

  /**
   * Handle incoming WebSocket message.
   */
  private _handleMessage(ws: WebSocket, state: IClientState, msg: IWsMessage): void {
    switch (msg.type) {
      case "subscribe":
        this._handleSubscribe(ws, state, msg as ISubscribeMessage);
        break;
      case "unsubscribe":
        this._handleUnsubscribe(state, msg as IUnsubscribeMessage);
        break;
      case "external:update":
        this._handleExternalUpdate(ws, msg as IExternalUpdateMessage);
        break;
      default:
        this._sendError(ws, `Unknown message type: ${msg.type}`, "unknown_message_type");
    }
  }

  private _handleExternalUpdate(ws: WebSocket, msg: IExternalUpdateMessage): void {
    if (!this._engine) {
      this._sendError(ws, "Engine not available", "engine_unavailable");
      return;
    }
    if (typeof msg.graphId !== "string" || msg.graphId.length === 0) {
      this._sendError(ws, "external:update requires graphId", "malformed_message");
      return;
    }
    if (typeof msg.nodeId !== "string" || msg.nodeId.length === 0) {
      this._sendError(ws, "external:update requires nodeId", "malformed_message");
      return;
    }
    if (!Array.isArray(msg.values)) {
      this._sendError(ws, "external:update values must be an array", "malformed_message");
      return;
    }

    const graph = this._engine.getGraph(msg.graphId);
    if (!graph) {
      this._sendError(ws, `Unknown graph: ${msg.graphId}`, "unknown_graph");
      return;
    }

    const node = graph.plan.nodes.get(msg.nodeId);
    if (!node) {
      this._sendError(ws, `Unknown node: ${msg.nodeId}`, "unknown_node");
      return;
    }
    if (!isExternalWritableNode(node)) {
      this._sendError(ws, `Node is not externally writable: ${msg.nodeId}`, "non_external_node");
      return;
    }

    const values = new Float32Array(msg.values.length);
    for (let i = 0; i < msg.values.length; i++) {
      const value = msg.values[i];
      if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) {
        this._sendError(ws, `Value at index ${i} must be a finite number in [0, 1]`, "invalid_value");
        return;
      }
      values[i] = value;
    }

    try {
      node.setExternalValues(values);
    } catch (err) {
      this._sendError(ws, (err as Error).message, "length_mismatch");
      return;
    }

    const ack: IExternalAckMessage = {
      type: "external:ack",
      graphId: msg.graphId,
      nodeId: msg.nodeId,
      size: values.length,
    };
    ws.send(JSON.stringify(ack));
  }

  /**
   * Handle subscribe message.
   */
  private _handleSubscribe(ws: WebSocket, state: IClientState, msg: ISubscribeMessage): void {
    const topic = msg.topic;

    if (topic === "metrics") {
      state.subscriptions.add("metrics");
      // Allow custom interval via payload
      const intervalMs = (msg.payload as { intervalMs?: number })?.intervalMs;
      if (typeof intervalMs === "number" && intervalMs >= this._minIntervalMs) {
        state.metricsIntervalMs = intervalMs;
      }
      this._updateMetricsTimer();

      // Send immediate metrics snapshot
      this._sendMetrics(ws);
    } else {
      this._sendError(ws, `Unknown topic: ${topic}`, "unknown_topic");
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
      if (state.subscriptions.has("metrics")) {
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
      if (state.subscriptions.has("metrics") && ws.readyState === WebSocket.OPEN) {
        this._sendMetrics(ws);
      }
    }
  }

  /**
   * Send metrics snapshot to a client.
   */
  private _sendMetrics(ws: WebSocket): void {
    if (!this._engine || ws.readyState !== WebSocket.OPEN) return;

    const engineStats = this._engine.getStats();
    const graphs: Record<string, any> = {};
    
    // Get stats for each graph
    for (const graphId of this._engine.listGraphs()) {
      const graph = this._engine.getGraph(graphId);
      if (graph) {
        graphs[graphId] = graph.getStats();
      }
    }

    const message: IMetricsMessage = {
      type: "metrics",
      timestamp: Date.now(),
      engineStats: {
        totalGraphs: engineStats.totalGraphs,
        runningGraphs: engineStats.runningGraphs,
        totalNodes: engineStats.totalNodes,
        uptimeMs: engineStats.uptimeMs,
      },
      graphs,
    };

    ws.send(JSON.stringify(message));
  }

  /**
   * Send error message to client.
   */
  private _sendError(ws: WebSocket, message: string, code?: string): void {
    if (ws.readyState !== WebSocket.OPEN) return;

    const msg: IErrorMessage = {
      type: "error",
      message,
      code,
    };

    ws.send(JSON.stringify(msg));
  }
}
