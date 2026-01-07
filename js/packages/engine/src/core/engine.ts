/**
 * Engine domain - top-level engine entity
 */

import type { ILogger } from "../nodes/index.js";
import type { IGraph, IGraphConfig } from "./graph.js";
import type { IEngineStats } from "./stats.js";
import { Graph } from "./graph.js";

export interface IEngineConfig {
  /** Logger for engine operations */
  logger: ILogger;
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
