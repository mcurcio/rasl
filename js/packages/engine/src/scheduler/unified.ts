/**
 * UnifiedScheduler - Pull-based scheduler for RASL graph execution.
 */

import {
  type INode,
  type InputPort,
  type OutputPort,
  type ITickContext,
  NodeContext,
  Frame,
  getInputs,
  getOutputs,
  getPullRate,
  createTickContext,
} from '../runtime/index.js';
import type { ExecutionPlan } from '../graph/plan.js';
import type { Edge } from '../graph/edge.js';
import { NodeMonitor, type INodeStats } from './monitor.js';

/**
 * Scheduler configuration options.
 */
export interface ISchedulerConfig {
  /**
   * Maximum time (ms) allowed for processing a frame before logging a warning.
   * Set to 0 to disable. Default: 16ms.
   */
  frameBudgetMs?: number;

  /**
   * Number of consecutive errors before a node is disabled.
   * Set to null to disable. Default: null.
   */
  maxConsecutiveErrors?: number | null;
}

/**
 * Simple console logger implementation.
 */
const consoleLogger = {
  debug: (msg: string, ...args: unknown[]) => console.debug(`[DEBUG] ${msg}`, ...args),
  info: (msg: string, ...args: unknown[]) => console.info(`[INFO] ${msg}`, ...args),
  warn: (msg: string, ...args: unknown[]) => console.warn(`[WARN] ${msg}`, ...args),
  error: (msg: string, ...args: unknown[]) => console.error(`[ERROR] ${msg}`, ...args),
};

/**
 * Pull-based scheduler for executing RASL graphs.
 *
 * The scheduler drives graph execution by:
 * 1. Starting all nodes in topological order
 * 2. Scheduling sink nodes at their declared frame rates
 * 3. Pulling data through the graph from sinks to sources
 * 4. Stopping all nodes on shutdown
 */
export class UnifiedScheduler {
  private readonly _plan: ExecutionPlan;
  private readonly _config: Required<ISchedulerConfig>;
  private readonly _monitor = new NodeMonitor();
  private readonly _disabledNodes = new Set<string>();
  private readonly _routes = new Map<string, Edge[]>();
  private readonly _outputFrames = new Map<string, Frame | null>();

  private _running = false;
  private _startTime = 0;
  private _tickCount = 0;
  private _lastNodeTime = new Map<string, number>();

  constructor(plan: ExecutionPlan, config?: ISchedulerConfig) {
    this._plan = plan;
    this._config = {
      frameBudgetMs: config?.frameBudgetMs ?? 16,
      maxConsecutiveErrors: config?.maxConsecutiveErrors ?? null,
    };

    // Build routing table: (source_node.port) -> list of edges
    for (const [source, edges] of plan.adjacency) {
      for (const edge of edges) {
        const key = `${source}.${edge.sourcePort}`;
        const existing = this._routes.get(key) ?? [];
        existing.push(edge);
        this._routes.set(key, existing);
      }
    }
  }

  /**
   * Access the node monitor for inspecting execution stats.
   */
  get monitor(): NodeMonitor {
    return this._monitor;
  }

  /**
   * Get execution statistics for nodes.
   */
  getNodeStats(nodeId?: string): INodeStats | Map<string, INodeStats> | null {
    if (nodeId !== undefined) {
      return this._monitor.getStats(nodeId);
    }
    return this._monitor.getAllStats();
  }

  /**
   * Run the scheduler until stopped.
   */
  async run(): Promise<void> {
    if (this._running) return;
    this._running = true;
    this._startTime = performance.now() / 1000;
    this._tickCount = 0;

    try {
      // Start all nodes in topological order
      await this._startNodes();

      // Find sinks and their frame rates
      const sinks = this._findSinks();

      // Main loop
      while (this._running) {
        const now = performance.now() / 1000;
        const t = now - this._startTime;

        // Pull from each sink
        for (const { node, intervalMs } of sinks) {
          const lastTime = this._lastNodeTime.get(node.id) ?? 0;
          const elapsed = (now - this._startTime) * 1000 - lastTime * 1000;

          if (elapsed >= intervalMs) {
            await this._pullNode(node, t);
            this._lastNodeTime.set(node.id, t);
          }
        }

        this._tickCount++;

        // Yield to event loop
        await this._sleep(1);
      }
    } finally {
      await this._stopNodes();
    }
  }

  /**
   * Run the scheduler for a specific duration.
   */
  async runFor(durationMs: number): Promise<void> {
    const endTime = performance.now() + durationMs;

    if (this._running) return;
    this._running = true;
    this._startTime = performance.now() / 1000;
    this._tickCount = 0;

    try {
      await this._startNodes();
      const sinks = this._findSinks();

      while (this._running && performance.now() < endTime) {
        const now = performance.now() / 1000;
        const t = now - this._startTime;

        for (const { node, intervalMs } of sinks) {
          const lastTime = this._lastNodeTime.get(node.id) ?? 0;
          const elapsed = (now - this._startTime) * 1000 - lastTime * 1000;

          if (elapsed >= intervalMs) {
            await this._pullNode(node, t);
            this._lastNodeTime.set(node.id, t);
          }
        }

        this._tickCount++;
        await this._sleep(1);
      }
    } finally {
      this._running = false;
      await this._stopNodes();
    }
  }

  /**
   * Stop the scheduler.
   */
  stop(): void {
    this._running = false;
  }

  private async _startNodes(): Promise<void> {
    for (const nodeId of this._plan.topologicalOrder) {
      const node = this._plan.nodes.get(nodeId);
      if (!node) continue;

      const ctx = this._createNodeContext(node);
      try {
        await node.start(ctx);
      } catch (error) {
        console.error(`Failed to start node '${nodeId}':`, error);
        this._disabledNodes.add(nodeId);
      }
    }
  }

  private async _stopNodes(): Promise<void> {
    // Stop in reverse order
    const reversed = [...this._plan.topologicalOrder].reverse();
    for (const nodeId of reversed) {
      const node = this._plan.nodes.get(nodeId);
      if (!node) continue;

      const ctx = this._createNodeContext(node);
      try {
        await node.stop(ctx);
      } catch (error) {
        console.error(`Failed to stop node '${nodeId}':`, error);
      }
    }
  }

  private _findSinks(): Array<{ node: INode; intervalMs: number }> {
    const sinks: Array<{ node: INode; intervalMs: number }> = [];

    for (const node of this._plan.nodes.values()) {
      // Check if node has pull rate - look on prototype method, not bound method
      const proto = Object.getPrototypeOf(node);
      const pullMethod = proto?.pull;
      const hz = getPullRate(pullMethod, node);

      if (hz !== null && hz > 0) {
        sinks.push({ node, intervalMs: 1000 / hz });
      }
    }

    return sinks;
  }

  private async _pullNode(node: INode, t: number): Promise<void> {
    if (this._disabledNodes.has(node.id)) return;

    const lastTime = this._lastNodeTime.get(node.id) ?? t;
    const dt = t - lastTime;

    const tick = createTickContext({
      tick: this._tickCount,
      t,
      dt,
      wallTime: performance.now() / 1000,
    });

    // Pull upstream nodes first
    await this._pullUpstream(node, tick);

    // Execute this node
    const startTime = performance.now();
    try {
      await node.pull(tick);
      const elapsedMs = performance.now() - startTime;
      this._monitor.recordSuccess(node.id, elapsedMs);

      // Check frame budget
      if (this._config.frameBudgetMs > 0 && elapsedMs > this._config.frameBudgetMs) {
        console.warn(
          `Node '${node.id}' exceeded frame budget: ${elapsedMs.toFixed(2)}ms > ${this._config.frameBudgetMs}ms`
        );
      }

      // Capture output frames
      const outputs = getOutputs(node);
      for (const port of outputs as unknown as Iterable<OutputPort>) {
        const frame = port._consume();
        if (frame) {
          this._outputFrames.set(`${node.id}.${port.name}`, frame);
        }
      }
    } catch (error) {
      const elapsedMs = performance.now() - startTime;
      const consecutive = this._monitor.recordFailure(node.id, error as Error, elapsedMs);

      console.error(`Node '${node.id}' failed:`, error);

      if (
        this._config.maxConsecutiveErrors !== null &&
        consecutive >= this._config.maxConsecutiveErrors
      ) {
        console.error(`Disabling node '${node.id}' after ${consecutive} consecutive failures`);
        this._disabledNodes.add(node.id);
      }
    }
  }

  private async _pullUpstream(node: INode, tick: ITickContext): Promise<void> {
    const inputs = getInputs(node);

    for (const inputPort of inputs as unknown as Iterable<InputPort>) {
      // Find edges targeting this port
      for (const [, edges] of this._routes) {
        for (const edge of edges) {
          if (edge.target === node.id && edge.targetPort === inputPort.name) {
            // Pull the source node
            const sourceNode = this._plan.nodes.get(edge.source);
            if (sourceNode && !this._disabledNodes.has(edge.source)) {
              await this._pullNode(sourceNode, tick.t);

              // Route the frame to the input port
              const frame = this._outputFrames.get(`${edge.source}.${edge.sourcePort}`);
              if (frame) {
                inputPort._setFrame(frame);
                inputPort._setHasUpstream(true);
              }
            }
          }
        }
      }
    }
  }

  private _createNodeContext(node: INode): NodeContext {
    return new NodeContext({
      nodeId: node.id,
      logger: consoleLogger,
      emit: async (port: string, frame: Frame) => {
        this._outputFrames.set(`${node.id}.${port}`, frame);
      },
      startBackground: (fn: () => Promise<void>) => {
        fn().catch((err) => console.error(`Background task failed:`, err));
      },
    });
  }

  private _sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
