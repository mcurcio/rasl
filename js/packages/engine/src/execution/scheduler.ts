/**
 * UnifiedScheduler - Pull-based scheduler for RASL graph execution.
 */

import type { Frame } from "../runtime/frame.js";
import {
  createTickContext,
  getInputs,
  getOutputs,
  getPullRate,
  type ILogger,
  type INode,
  type ITickContext,
  NodeContext,
} from "../runtime/index.js";

import type { Edge } from "../graph/edge.js";
import type { ExecutionPlan } from "../graph/plan.js";
import { childLogger, createConsoleLogger } from "../log/index.js";
import { type INodeStats, NodeMonitor } from "./monitor.js";
import { applyEdgeRouting, validateNonOverlappingTargets } from "./routing.js";

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

  /**
   * Logger to use for scheduler + node lifecycle logs.
   * Defaults to a simple console logger.
   */
  logger?: ILogger;
}

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
  private readonly _logger: ILogger;
  private readonly _monitor = new NodeMonitor();
  private readonly _disabledNodes = new Set<string>();
  private readonly _routes = new Map<string, Edge[]>();
  private readonly _outputFrames = new Map<string, Frame | null>();

  private _running = false;
  private _startTime = 0;
  private _tickCount = 0;

  /**
   * Per-node last pull time (seconds since start) for dt calculation.
   */
  private readonly _lastPulledTime = new Map<string, number>();

  /**
   * Per-tick memoization: which tick each node was last pulled.
   */
  private readonly _lastPulledTick = new Map<string, number>();

  /**
   * Re-entrancy guard: nodes currently being pulled (for cycle detection).
   */
  private readonly _inProgress = new Set<string>();

  constructor(plan: ExecutionPlan, config?: ISchedulerConfig) {
    this._plan = plan;
    this._logger = config?.logger ?? createConsoleLogger();
    this._config = {
      frameBudgetMs: config?.frameBudgetMs ?? 16,
      maxConsecutiveErrors: config?.maxConsecutiveErrors ?? null,
      logger: this._logger,
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

    // Validate non-overlapping target slices at startup
    this._validateTargetSlices();

    this._logger.debug("Graph built", {
      nodes: plan.nodes.size,
      edges: Array.from(plan.adjacency.values()).reduce((acc, e) => acc + e.length, 0),
    });
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

    this._logger.info("Scheduler starting");

    try {
      // Start all nodes in topological order
      await this._startNodes();

      // Find sinks and their frame rates
      const sinks = this._findSinks();

      this._logger.debug("Sinks found", {
        sinks: sinks.map((s) => ({ nodeId: s.node.id, intervalMs: s.intervalMs })),
      });

      // Main loop
      while (this._running) {
        const now = performance.now() / 1000;
        const t = now - this._startTime;

        // Pull from each sink
        // Increment tick at start of frame
        this._tickCount++;

        for (const { node, intervalMs } of sinks) {
          const lastPulledTime = this._lastPulledTime.get(node.id) ?? 0;
          const elapsed = (t - lastPulledTime) * 1000;

          if (elapsed >= intervalMs) {
            this._logger.trace("Pulling sink", { nodeId: node.id, t, elapsedMs: elapsed });
            await this._pullNode(node, t);
          }
        }

        // Yield to event loop
        await this._sleep(1);
      }
    } finally {
      this._logger.info("Scheduler stopping");
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

        // Increment tick at start of frame
        this._tickCount++;

        for (const { node, intervalMs } of sinks) {
          const lastPulledTime = this._lastPulledTime.get(node.id) ?? 0;
          const elapsed = (t - lastPulledTime) * 1000;

          if (elapsed >= intervalMs) {
            await this._pullNode(node, t);
          }
        }
        await this._sleep(1);
      }
    } finally {
      this._running = false;
      this._logger.info("Scheduler stopping (runFor)");
      await this._stopNodes();
    }
  }

  /**
   * Stop the scheduler.
   */
  stop(): void {
    this._logger.info("Scheduler stop requested");
    this._running = false;
  }

  private async _startNodes(): Promise<void> {
    for (const nodeId of this._plan.topologicalOrder) {
      const node = this._plan.nodes.get(nodeId);
      if (!node) continue;

      const ctx = this._createNodeContext(node);
      try {
        this._logger.debug("Starting node", { nodeId });
        await node.start(ctx);
        this._logger.debug("Node started", { nodeId });
      } catch (error) {
        this._logger.error(`Failed to start node '${nodeId}'`, error as Error, { nodeId });
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
        this._logger.debug("Stopping node", { nodeId });
        await node.stop(ctx);
        this._logger.debug("Node stopped", { nodeId });
      } catch (error) {
        this._logger.error(`Failed to stop node '${nodeId}'`, error as Error, { nodeId });
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

    // Per-tick memoization: skip if already pulled this tick
    const lastPulledTick = this._lastPulledTick.get(node.id);
    if (lastPulledTick === this._tickCount) {
      this._logger.trace("Node already pulled this tick (memoized)", { nodeId: node.id, tick: this._tickCount });
      return;
    }

    // Re-entrancy guard: if we're already pulling this node, serve previous output
    if (this._inProgress.has(node.id)) {
      this._logger.trace("Cycle detected, serving previous tick output", { nodeId: node.id, tick: this._tickCount });
      return;
    }

    // Mark as in-progress for cycle detection
    this._inProgress.add(node.id);

    try {
      // Calculate dt from last pull time (not last sink time)
      const lastPulledTime = this._lastPulledTime.get(node.id) ?? 0;
      const dt = lastPulledTime === 0 ? 0 : t - lastPulledTime;

      const tick = createTickContext({
        tick: this._tickCount,
        t,
        dt,
        wallTime: performance.now() / 1000,
      });

      // Pull upstream nodes first
      await this._pullUpstream(node, tick);

      // Execute this node
      await this._executeNode(node, tick);

      // Update tracking after successful pull
      this._lastPulledTick.set(node.id, this._tickCount);
      this._lastPulledTime.set(node.id, t);
    } finally {
      this._inProgress.delete(node.id);
    }
  }

  private async _executeNode(node: INode, tick: ITickContext): Promise<void> {
    const startTime = performance.now();
    try {
      this._logger.trace("Execute node", { nodeId: node.id, tick: tick.tick, t: tick.t, dt: tick.dt });
      await node.pull(tick);
      const elapsedMs = performance.now() - startTime;
      this._monitor.recordSuccess(node.id, elapsedMs);

      // Check frame budget
      if (this._config.frameBudgetMs > 0 && elapsedMs > this._config.frameBudgetMs) {
        this._logger.warn("Frame budget exceeded", {
          nodeId: node.id,
          elapsedMs,
          frameBudgetMs: this._config.frameBudgetMs,
        });
      }

      // Capture output frames
      const outputs = getOutputs(node);
      for (const port of outputs) {
        const frame = port._consume();
        if (frame) {
          this._outputFrames.set(`${node.id}.${port.name}`, frame);
        }
      }
    } catch (error) {
      const elapsedMs = performance.now() - startTime;
      const consecutive = this._monitor.recordFailure(node.id, error as Error, elapsedMs);

      this._logger.error("Node execution failed", error as Error, {
        nodeId: node.id,
        elapsedMs,
        consecutiveFailures: consecutive,
      });

      if (this._config.maxConsecutiveErrors !== null && consecutive >= this._config.maxConsecutiveErrors) {
        this._logger.error(`Disabling node '${node.id}' after ${consecutive} consecutive failures`, undefined, { nodeId: node.id, consecutiveFailures: consecutive });
        this._disabledNodes.add(node.id);
      }
    }
  }

  private async _pullUpstream(node: INode, tick: ITickContext): Promise<void> {
    const inputs = getInputs(node);

    for (const inputPort of inputs) {
      // Find edges targeting this port
      for (const [, edges] of this._routes) {
        for (const edge of edges) {
          if (edge.target === node.id && edge.targetPort === inputPort.name) {
            // Pull the source node
            const sourceNode = this._plan.nodes.get(edge.source);
            if (sourceNode && !this._disabledNodes.has(edge.source)) {
              this._logger.trace("Routing edge", {
                source: edge.source,
                sourcePort: edge.sourcePort,
                target: edge.target,
                targetPort: edge.targetPort,
              });
              await this._pullNode(sourceNode, tick.t);

              // Route the frame to the input port with slice/repeat applied
              const frame = this._outputFrames.get(`${edge.source}.${edge.sourcePort}`);
              if (frame) {
                try {
                  const routedFrame = applyEdgeRouting(frame, edge);
                  inputPort._setFrame(routedFrame);
                  inputPort._setHasUpstream(true);
                } catch (err) {
                  this._logger.error("Frame routing failed", err as Error, {
                    source: edge.source,
                    sourcePort: edge.sourcePort,
                    target: edge.target,
                    targetPort: edge.targetPort,
                  });
                }
              }
            }
          }
        }
      }
    }
  }

  private _createNodeContext(node: INode): NodeContext {
    const logger = childLogger(this._logger, { nodeId: node.id });
    return new NodeContext({
      nodeId: node.id,
      logger,
      emit: async (port: string, frame: Frame) => {
        this._outputFrames.set(`${node.id}.${port}`, frame);
      },
      startBackground: (fn: () => Promise<void>) => {
        fn().catch((err) => logger.error("Background task failed", err as Error));
      },
    });
  }

  private _sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * Validate that no target slices overlap for the same input port.
   * Called at startup to fail fast on invalid configurations.
   */
  private _validateTargetSlices(): void {
    // Group edges by target port
    const edgesByTarget = new Map<string, Edge[]>();

    for (const edges of this._plan.adjacency.values()) {
      for (const edge of edges) {
        const key = `${edge.target}.${edge.targetPort}`;
        const existing = edgesByTarget.get(key) ?? [];
        existing.push(edge);
        edgesByTarget.set(key, existing);
      }
    }

    // Validate each group
    for (const [targetKey, edges] of edgesByTarget) {
      if (edges.length > 1) {
        try {
          validateNonOverlappingTargets(edges);
        } catch (err) {
          this._logger.error("Invalid target slice configuration", err as Error, { targetKey });
          throw err;
        }
      }
    }
  }
}
