/**
 * RASL HTTP/WebSocket server.
 */

import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";

import type { IGraphDescription, INodeStats, ILogger, IEngine } from "@rasl/engine";
import { WsHandler } from "./ws-handler.js";

/**
 * Server configuration.
 */
export interface IServerConfig {
  port: number;
  host?: string;
  staticDir?: string;
  corsOrigins?: string[];
  /** Enable WebSocket support (default: true) */
  enableWebSocket?: boolean;
  /** Logger for server operations */
  logger: ILogger;
}

/**
 * RASL server for runtime control and monitoring.
 */
export class RaslServer {
  private readonly _config: IServerConfig;
  private _engine: IEngine | null = null;
  private _server: Server | null = null;
  private _wsHandler: WsHandler | null = null;
  private _running = false;
  private _startTime = 0;

  constructor(config: IServerConfig) {
    this._config = {
      port: config.port,
      host: config.host ?? "localhost",
      staticDir: config.staticDir ?? "./public",
      corsOrigins: config.corsOrigins ?? ["*"],
      enableWebSocket: config.enableWebSocket ?? true,
      logger: config.logger,
    };
  }

  /**
   * Start the server with an engine.
   */
  async start(engine: IEngine): Promise<void> {
    if (this._running) return;

    this._engine = engine;
    this._startTime = Date.now();

    this._server = createServer((req, res) => this._handleRequest(req, res));

    return new Promise((resolve, reject) => {
      this._server!.on("error", reject);
      this._server!.listen(this._config.port, this._config.host, () => {
        this._running = true;

        // Attach WebSocket handler if enabled
        if (this._config.enableWebSocket) {
          this._wsHandler = new WsHandler();
          this._wsHandler.attach(this._server!, engine);
        }

        this._config.logger?.info(`RASL server started at http://${this._config.host}:${this._config.port}`);
        resolve();
      });
    });
  }

  /**
   * Stop the server.
   */
  async stop(): Promise<void> {
    if (!this._running || !this._server) return;

    // Detach WebSocket handler first
    if (this._wsHandler) {
      this._wsHandler.detach();
      this._wsHandler = null;
    }

    return new Promise((resolve) => {
      this._server!.close(() => {
        this._running = false;
        this._scheduler = null;
        this._server = null;
        resolve();
      });
    });
  }

  /**
   * Check if server is running.
   */
  get isRunning(): boolean {
    return this._running;
  }

  /**
   * Get the current scheduler.
   */
  getScheduler(): UnifiedScheduler | null {
    return this._scheduler;
  }

  /**
   * Get the server URL.
   */
  get url(): string {
    return `http://${this._config.host}:${this._config.port}`;
  }

  /**
   * Handle incoming HTTP requests.
   */
  private _handleRequest(req: IncomingMessage, res: ServerResponse): void {
    const url = new URL(req.url ?? "/", `http://${req.headers.host}`);
    const path = url.pathname;

    // Set CORS headers
    this._setCorsHeaders(res);

    // Handle preflight
    if (req.method === "OPTIONS") {
      res.writeHead(204);
      res.end();
      return;
    }

    // Route requests
    if (req.method === "GET") {
      if (path === "/health") {
        this._handleHealth(res);
      } else if (path === "/graph") {
        this._handleGraph(res);
      } else if (path === "/stats") {
        this._handleStats(res);
      } else if (path.startsWith("/node/")) {
        const nodeId = path.slice(6); // Remove '/node/' prefix
        this._handleNode(res, nodeId);
      } else {
        this._sendJson(res, 404, { error: "Not found" });
      }
    } else {
      this._sendJson(res, 405, { error: "Method not allowed" });
    }
  }

  /**
   * Set CORS headers on response.
   */
  private _setCorsHeaders(res: ServerResponse): void {
    const origins = this._config.corsOrigins;
    if (origins?.includes("*")) {
      res.setHeader("Access-Control-Allow-Origin", "*");
    } else if (origins && origins.length > 0) {
      res.setHeader("Access-Control-Allow-Origin", origins[0]);
    }
    res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  }

  /**
   * Send JSON response.
   */
  private _sendJson(res: ServerResponse, status: number, data: unknown): void {
    res.writeHead(status, { "Content-Type": "application/json" });
    res.end(JSON.stringify(data));
  }

  /**
   * Handle GET /health
   */
  private _handleHealth(res: ServerResponse): void {
    const response: IHealthResponse = {
      status: "ok",
      version: "0.1.0",
      uptime: (Date.now() - this._startTime) / 1000,
    };
    this._sendJson(res, 200, response);
  }

  /**
   * Handle GET /graph
   */
  private _handleGraph(res: ServerResponse): void {
    if (!this._scheduler) {
      this._sendJson(res, 503, { error: "Scheduler not available" });
      return;
    }

    // Access the plan from scheduler (need to expose this)
    const plan = (this._scheduler as unknown as { _plan: { describe(): IGraphDescription } })._plan;
    const response: IGraphResponse = {
      graph: plan.describe(),
    };
    this._sendJson(res, 200, response);
  }

  /**
   * Handle GET /stats
   */
  private _handleStats(res: ServerResponse): void {
    if (!this._scheduler) {
      this._sendJson(res, 503, { error: "Scheduler not available" });
      return;
    }

    const allStats = this._scheduler.getNodeStats() as Map<string, INodeStats> | null;
    const nodes: Record<string, INodeStats> = {};
    if (allStats) {
      for (const [id, stats] of allStats) {
        nodes[id] = stats;
      }
    }

    const response: IStatsResponse = {
      running: this._running,
      tickCount: 0, // TODO: expose from scheduler
      uptime: (Date.now() - this._startTime) / 1000,
      nodes,
    };
    this._sendJson(res, 200, response);
  }

  /**
   * Handle GET /node/:id
   */
  private _handleNode(res: ServerResponse, nodeId: string): void {
    if (!this._scheduler) {
      this._sendJson(res, 503, { error: "Scheduler not available" });
      return;
    }

    const plan = (this._scheduler as unknown as { _plan: { nodes: Map<string, unknown> } })._plan;
    const node = plan.nodes.get(nodeId) as
      | { id: string; inputs?: { names: string[] }; outputs?: { names: string[] }; constructor: { name: string } }
      | undefined;

    if (!node) {
      this._sendJson(res, 404, { error: `Node '${nodeId}' not found` });
      return;
    }

    const stats = this._scheduler.getNodeStats(nodeId) as INodeStats | null;

    const response: INodeResponse = {
      id: node.id,
      type: node.constructor.name,
      inputs: node.inputs?.names ?? [],
      outputs: node.outputs?.names ?? [],
      stats,
    };
    this._sendJson(res, 200, response);
  }
}
