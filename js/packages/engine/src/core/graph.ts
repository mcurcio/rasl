/**
 * Graph domain - core graph entity and interfaces
 */

import type { INodeStats } from "../execution/monitor.js";
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

  /** Get execution statistics for one node or all nodes */
  getNodeStats(nodeId?: string): INodeStats | Map<string, INodeStats> | null;
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
  private _runPromise: Promise<void> | null = null;

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
    
    this._runPromise = this._scheduler.run().catch((err: Error) => {
      this._running = false;
      this._logger.error(`Graph '${this.id}' scheduler failed`, err);
    });
  }

  async stop(): Promise<void> {
    if (!this._running) return;
    
    this._running = false;
    this._logger.info(`Graph '${this.id}' stopped`);
    
    // Graph stops its own scheduler
    this._scheduler.stop();
    await this._runPromise;
    this._runPromise = null;
  }

  getStats(): IGraphStats {
    return {
      nodeCount: this.plan.nodes.size,
      currentFps: 30, // Will be discovered from sinks
      framesProcessed: this._scheduler.tickCount,
      avgFrameTimeMs: 1000 / 30,
    };
  }

  getNodeStats(nodeId?: string): INodeStats | Map<string, INodeStats> | null {
    return this._scheduler.getNodeStats(nodeId);
  }
}
