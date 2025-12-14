/**
 * RASL HTTP/WebSocket server.
 */

import type { UnifiedScheduler } from '@rasl/engine';

/**
 * Server configuration.
 */
export interface IServerConfig {
  port: number;
  host?: string;
  staticDir?: string;
  corsOrigins?: string[];
}

/**
 * RASL server for runtime control and monitoring.
 */
export class RaslServer {
  private readonly _config: Required<IServerConfig>;
  private _scheduler: UnifiedScheduler | null = null;
  private _running = false;

  constructor(config: IServerConfig) {
    this._config = {
      port: config.port,
      host: config.host ?? 'localhost',
      staticDir: config.staticDir ?? './public',
      corsOrigins: config.corsOrigins ?? ['*'],
    };
  }

  /**
   * Start the server with a scheduler.
   */
  async start(scheduler: UnifiedScheduler): Promise<void> {
    this._scheduler = scheduler;
    this._running = true;

    // TODO: Implement HTTP server with native Node.js http module
    // TODO: Implement WebSocket server
    // TODO: Serve static files from staticDir

    console.log(
      `RASL server started at http://${this._config.host}:${this._config.port}`
    );
  }

  /**
   * Stop the server.
   */
  async stop(): Promise<void> {
    this._running = false;
    this._scheduler = null;

    // TODO: Close HTTP and WebSocket connections
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
}
