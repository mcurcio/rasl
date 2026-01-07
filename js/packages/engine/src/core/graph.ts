/**
 * Graph domain - core graph entity and interfaces
 */

import type { ILogger } from "../nodes/index.js";
import type { ExecutionPlan } from "../execution/plan.js";
import type { UnifiedScheduler } from "../execution/scheduler.js";
import { UnifiedScheduler as SchedulerImpl } from "../execution/scheduler.js";
import type { IGraphStats } from "./stats.js";

export interface IGraphConfig {
  /** Unique identifier for this graph */
  id: string;
  /** Execution plan for this graph */
  plan: ExecutionPlan;
  /** Whether this graph should auto-start when engine starts */
  autoStart?: boolean;
}

export interface IGraph {
  /** Unique graph identifier */
  readonly id: string;
  /** Execution plan */
  readonly plan: ExecutionPlan;
  /** Whether this graph is currently running */
  get isRunning(): boolean;
  
  /** Start this graph */
  start(): Promise<void>;
  
  /** Stop this graph */
  stop(): Promise<void>;
  
  /** Get graph statistics */
  getStats(): IGraphStats;
}

/**
 * Graph implementation
 */
export class Graph implements IGraph {
  readonly id: string;
  readonly plan: ExecutionPlan;
  readonly _autoStart: boolean;
  private readonly _scheduler: UnifiedScheduler;
  private _running = false;

  constructor(config: IGraphConfig, private readonly _logger: ILogger) {
    this.id = config.id;
    this.plan = config.plan;
    this._autoStart = config.autoStart ?? true;
    
    // Graph creates and owns its scheduler
    this._scheduler = new SchedulerImpl(this.plan, { logger: this._logger });
  }

  get isRunning(): boolean {
    return this._running;
  }

  async start(): Promise<void> {
    if (this._running) return;
    
    this._running = true;
    this._logger.info(`Graph '${this.id}' started`);
    
    // Graph manages its own scheduler
    await this._scheduler.run();
  }

  async stop(): Promise<void> {
    if (!this._running) return;
    
    this._running = false;
    this._logger.info(`Graph '${this.id}' stopped`);
    
    // Graph stops its own scheduler
    this._scheduler.stop();
  }

  getStats(): IGraphStats {
    // TODO: Implement real stats collection from scheduler
    return {
      nodeCount: this.plan.nodes.size,
      currentFps: 30, // Will be discovered from sinks
      framesProcessed: 0,
      avgFrameTimeMs: 1000 / 30,
    };
  }
}
