/**
 * BaseNode - Abstract base class for all RASL nodes.
 */

import type { Metadata } from "../runtime/frame.js";
import { EMPTY_METADATA } from "../runtime/frame.js";
import type { ITickContext } from "../runtime/tick.js";
import type { NodeContext } from "./context.js";

/**
 * Base configuration shared by all nodes.
 */
export interface IBaseNodeConfig {
  id: string;
  metadata?: Record<string, string>;
}

/**
 * Abstract base class for all nodes.
 *
 * Subclasses must:
 * 1. Call super(config) in their constructor
 * 2. Implement pull(tick) for computation
 * 3. Define inputs and/or outputs PortGroups as class properties
 *
 * The base class handles:
 * - Setting this.id from config
 * - Storing metadata
 */
export abstract class BaseNode {
  /**
   * Unique node identifier within the graph.
   */
  readonly id: string;

  /**
   * Metadata attached to frames emitted by this node.
   */
  protected readonly _metadata: Metadata;

  constructor(config: IBaseNodeConfig) {
    this.id = config.id;
    this._metadata = config.metadata ? Object.freeze({ ...config.metadata }) : EMPTY_METADATA;
  }

  /**
   * Initialize the node when scheduler starts.
   * Override in subclasses that need initialization.
   */
  async start(_ctx: NodeContext): Promise<void> {
    // Default: no-op
  }

  /**
   * Process inputs and produce outputs.
   * Override in subclasses to implement node logic.
   */
  async pull(_tick: ITickContext): Promise<void> {
    // Default: no-op
  }

  /**
   * Clean up the node during graceful shutdown.
   * Override in subclasses that need cleanup.
   */
  async stop(_ctx: NodeContext): Promise<void> {
    // Default: no-op
  }
}
