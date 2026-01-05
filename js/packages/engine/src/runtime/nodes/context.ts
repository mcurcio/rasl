/**
 * NodeContext - Runtime context provided to nodes.
 */

import type { Frame } from "../frame.js";

/**
 * Logger interface for node logging.
 */
export type LogFields = Record<string, unknown>;

export interface ILogger {
  trace(a0: unknown, ...args: unknown[]): void;
  debug(a0: unknown, ...args: unknown[]): void;
  info(a0: unknown, ...args: unknown[]): void;
  warn(a0: unknown, ...args: unknown[]): void;
  error(a0: unknown, ...args: unknown[]): void;
}

/**
 * Runtime context provided to nodes during execution.
 *
 * Provides access to runtime services like logging, frame emission,
 * and background task spawning.
 */
export class NodeContext {
  /**
   * The node's unique identifier.
   */
  readonly nodeId: string;

  /**
   * Logger bound to this node.
   */
  readonly logger: ILogger;

  private readonly _emit: (port: string, frame: Frame) => Promise<void>;
  private readonly _startBackground: (fn: () => Promise<void>) => void;

  constructor(options: {
    nodeId: string;
    logger: ILogger;
    emit: (port: string, frame: Frame) => Promise<void>;
    startBackground: (fn: () => Promise<void>) => void;
  }) {
    this.nodeId = options.nodeId;
    this.logger = options.logger;
    this._emit = options.emit;
    this._startBackground = options.startBackground;
  }

  /**
   * Emit a frame on an output port.
   * Routes the frame to all connected downstream nodes.
   */
  async emit(port: string, frame: Frame): Promise<void> {
    return this._emit(port, frame);
  }

  /**
   * Start a background task that runs alongside the node.
   */
  startBackground(fn: () => Promise<void>): void {
    this._startBackground(fn);
  }
}
