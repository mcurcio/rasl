/**
 * RASL Engine - Top-level object in the ecosystem
 * 
 * The Engine is the main entry point that manages one or more Graphs.
 * Each Graph owns its own scheduler for execution.
 */

import type { ILogger } from "../runtime/nodes/index.js";
import type { ExecutionPlan } from "../graph/plan.js";
import { ExecutionPlan as ExecutionPlanImpl } from "../graph/plan.js";
import type { UnifiedScheduler } from "../scheduler/unified.js";
import { UnifiedScheduler as SchedulerImpl } from "../scheduler/unified.js";

export interface IEngineConfig {
  /** Logger for engine operations */
  logger: ILogger;
}

export interface IGraphConfig {
  /** Unique identifier for this graph */
  id: string;
  /** Execution plan for this graph */
  plan: ExecutionPlan;
  /** Whether this graph should auto-start when engine starts */
  autoStart?: boolean;
}

export interface IEngine {
  /** Add a graph to the engine */
  addGraph(config: IGraphConfig): void;
  
  /** Remove a graph from the engine */
  removeGraph(id: string): void;
  
  /** Get a graph by ID */
  getGraph(id: string): IGraph | undefined;
  
  /** List all graph IDs */
  listGraphs(): string[];
  
  /** Start the engine and all auto-start graphs */
  start(): Promise<void>;
  
  /** Stop the engine and all running graphs */
  stop(): Promise<void>;
  
  /** Start a specific graph */
  startGraph(id: string): Promise<void>;
  
  /** Stop a specific graph */
  stopGraph(id: string): Promise<void>;
  
  /** Check if engine is running */
  get isRunning(): boolean;
  
  /** Get engine statistics */
  getStats(): IEngineStats;
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

export interface IEngineStats {
  /** Total graphs managed */
  totalGraphs: number;
  /** Currently running graphs */
  runningGraphs: number;
  /** Total nodes across all graphs */
  totalNodes: number;
  /** Engine uptime in milliseconds */
  uptimeMs: number;
}

export interface IGraphStats {
  /** Number of nodes in this graph */
  nodeCount: number;
  /** Current frame rate */
  currentFps: number;
  /** Frames processed since start */
  framesProcessed: number;
  /** Average frame time in milliseconds */
  avgFrameTimeMs: number;
}

/**
 * RASL Engine implementation
 */
export class Engine implements IEngine {
  private readonly _config: IEngineConfig;
  private readonly _graphs = new Map<string, IGraph>();
  private _running = false;
  private _startTime = 0;

  constructor(config: IEngineConfig) {
    this._config = config;
  }

  addGraph(config: IGraphConfig): void {
    if (this._graphs.has(config.id)) {
      throw new Error(`Graph '${config.id}' already exists`);
    }

    const graph = new Graph(config, this._config.logger);
    this._graphs.set(config.id, graph);

    this._config.logger.info(`Added graph '${config.id}' with ${config.plan.nodes.size} nodes`);
  }

  removeGraph(id: string): void {
    const graph = this._graphs.get(id);
    if (!graph) {
      throw new Error(`Graph '${id}' not found`);
    }

    if (graph.isRunning) {
      void graph.stop();
    }

    this._graphs.delete(id);
    this._config.logger.info(`Removed graph '${id}'`);
  }

  listGraphs(): string[] {
    return Array.from(this._graphs.keys());
  }

  getGraph(id: string): IGraph | undefined {
    return this._graphs.get(id);
  }

  async start(): Promise<void> {
    if (this._running) return;

    this._running = true;
    this._startTime = Date.now();

    // Start all auto-start graphs
    const autoStartGraphs = Array.from(this._graphs.values())
      .filter(graph => (graph as Graph)._autoStart);

    if (autoStartGraphs.length === 0) {
      this._config.logger.warn("No graphs configured for auto-start");
      return;
    }

    this._config.logger.info(`Starting ${autoStartGraphs.length} graphs`);
    
    // Start all graphs in parallel
    const startPromises = autoStartGraphs.map(graph => graph.start());
    await Promise.all(startPromises);

    this._config.logger.info("Engine started");
  }

  async stop(): Promise<void> {
    if (!this._running) return;

    this._running = false;

    // Stop all running graphs
    const runningGraphs = Array.from(this._graphs.values())
      .filter(graph => graph.isRunning);

    if (runningGraphs.length > 0) {
      this._config.logger.info(`Stopping ${runningGraphs.length} graphs`);
      
      const stopPromises = runningGraphs.map(graph => graph.stop());
      await Promise.all(stopPromises);
    }

    this._config.logger.info("Engine stopped");
  }

  async startGraph(id: string): Promise<void> {
    const graph = this._graphs.get(id);
    if (!graph) {
      throw new Error(`Graph '${id}' not found`);
    }

    await graph.start();
  }

  async stopGraph(id: string): Promise<void> {
    const graph = this._graphs.get(id);
    if (!graph) {
      throw new Error(`Graph '${id}' not found`);
    }

    await graph.stop();
  }

  get isRunning(): boolean {
    return this._running;
  }

  getStats(): IEngineStats {
    const runningGraphs = Array.from(this._graphs.values())
      .filter(graph => graph.isRunning);

    return {
      totalGraphs: this._graphs.size,
      runningGraphs: runningGraphs.length,
      totalNodes: Array.from(this._graphs.values())
        .reduce((sum, graph) => sum + graph.plan.nodes.size, 0),
      uptimeMs: this._running ? Date.now() - this._startTime : 0,
    };
  }
}

/**
 * Graph implementation
 */
class Graph implements IGraph {
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
