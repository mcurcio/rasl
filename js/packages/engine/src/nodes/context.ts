/**
 * NodeContext - Runtime context provided to nodes.
 */

import type { Frame } from "../frame.js";

/**
 * Logger interface for node logging.
 */
export type LogFields = Record<string, unknown>;

export interface ILogger {
  // Standard pattern: message first, fields optional
  trace(message: string, fields?: Record<string, unknown>): void;
  debug(message: string, fields?: Record<string, unknown>): void;
  info(message: string, fields?: Record<string, unknown>): void;
  warn(message: string, fields?: Record<string, unknown>): void;
  
  // Error patterns
  error(message: string, error?: Error, fields?: Record<string, unknown>): void;
  
  // Create child logger with additional bindings
  child(bindings: Record<string, unknown>): ILogger;
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
