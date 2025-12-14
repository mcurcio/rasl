/**
 * GraphBuilder - Assembles nodes and edges into an ExecutionPlan.
 */

import { type INode, getInputs, getOutputs } from '../runtime/index.js';
import { Edge, type IConnectOptions } from './edge.js';
import { ExecutionPlan } from './plan.js';

/**
 * Warning emitted when cycles are detected in the graph.
 */
export class CycleWarning extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'CycleWarning';
  }
}

/**
 * Builder for assembling and validating the processing graph.
 *
 * Provides a fluent interface for constructing the graph:
 * add nodes, connect them with edges, then build() to get an ExecutionPlan.
 */
export class GraphBuilder {
  private readonly _nodes = new Map<string, INode>();
  private readonly _edges: Edge[] = [];

  /**
   * Read-only access to registered nodes.
   */
  get nodes(): Map<string, INode> {
    return new Map(this._nodes);
  }

  /**
   * Read-only access to registered edges.
   */
  get edges(): readonly Edge[] {
    return [...this._edges];
  }

  /**
   * Register a node with the graph.
   */
  addNode(node: INode): void {
    if (this._nodes.has(node.id)) {
      throw new Error(`Duplicate node id '${node.id}'`);
    }
    this._nodes.set(node.id, node);
  }

  /**
   * Create an edge connecting two node ports.
   */
  connect(
    source: string,
    sourcePort: string,
    target: string,
    targetPort: string,
    options?: IConnectOptions
  ): void {
    if (!this._nodes.has(source)) {
      throw new Error(`Unknown source node '${source}'`);
    }
    if (!this._nodes.has(target)) {
      throw new Error(`Unknown target node '${target}'`);
    }

    const srcNode = this._nodes.get(source)!;
    const tgtNode = this._nodes.get(target)!;

    const srcOutputs = getOutputs(srcNode);
    const tgtInputs = getInputs(tgtNode);

    // Validate port existence
    if (!srcOutputs.has(sourcePort)) {
      throw new Error(
        `Node '${source}' has no output port '${sourcePort}'. ` +
        `Available: ${srcOutputs.names.join(', ')}`
      );
    }
    if (!tgtInputs.has(targetPort)) {
      throw new Error(
        `Node '${target}' has no input port '${targetPort}'. ` +
        `Available: ${tgtInputs.names.join(', ')}`
      );
    }

    // Validate slice compatibility if both are specified
    if (options?.sourceSlice && options?.targetSlice) {
      const srcSpec = srcOutputs.get(sourcePort)!.spec;
      const tgtSpec = tgtInputs.get(targetPort)!.spec;

      const srcLen = Edge.sliceLength(options.sourceSlice, srcSpec.fixedCount);
      const tgtLen = Edge.sliceLength(options.targetSlice, tgtSpec.fixedCount);

      if (srcLen !== null && tgtLen !== null && srcLen !== tgtLen) {
        throw new Error(
          `Slice length mismatch: ${source}.${sourcePort} has ${srcLen} channels, ` +
          `but ${target}.${targetPort} has ${tgtLen} channels`
        );
      }
    }

    this._edges.push(new Edge(source, sourcePort, target, targetPort, options));
  }

  /**
   * Connect default output of source to default input of target.
   */
  connectDefault(source: string, target: string): void {
    if (!this._nodes.has(source)) {
      throw new Error(`Unknown source node '${source}'`);
    }
    if (!this._nodes.has(target)) {
      throw new Error(`Unknown target node '${target}'`);
    }

    const srcOutputs = getOutputs(this._nodes.get(source)!);
    const tgtInputs = getInputs(this._nodes.get(target)!);

    const [srcPortName] = srcOutputs.getDefault();
    const [tgtPortName] = tgtInputs.getDefault();

    this.connect(source, srcPortName, target, tgtPortName);
  }

  /**
   * Build the execution plan.
   */
  build(): ExecutionPlan {
    const adjacency = new Map<string, Edge[]>();

    // Initialize adjacency list
    for (const nodeId of this._nodes.keys()) {
      adjacency.set(nodeId, []);
    }

    // Populate adjacency list
    for (const edge of this._edges) {
      adjacency.get(edge.source)!.push(edge);
    }

    // Compute topological order
    const { order, cycles } = this._toposortWithCycles(adjacency);

    // Warn about cycles
    if (cycles.length > 0) {
      console.warn(
        `Graph contains ${cycles.length} cycle(s). ` +
        `Cycles may cause nodes to receive stale data on the first frame.`
      );
    }

    return new ExecutionPlan(this._nodes, adjacency, order);
  }

  /**
   * Compute execution order, handling cycles gracefully.
   */
  private _toposortWithCycles(
    adjacency: Map<string, Edge[]>
  ): { order: string[]; cycles: string[][] } {
    const cycles = this._findCycles(adjacency);

    const indegree = new Map<string, number>();
    for (const nodeId of this._nodes.keys()) {
      indegree.set(nodeId, 0);
    }

    for (const edges of adjacency.values()) {
      for (const edge of edges) {
        indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1);
      }
    }

    const queue: string[] = [];
    for (const [nodeId, deg] of indegree) {
      if (deg === 0) queue.push(nodeId);
    }

    const order: string[] = [];
    const remaining = new Set(this._nodes.keys());

    while (remaining.size > 0) {
      let node: string;
      if (queue.length > 0) {
        node = queue.shift()!;
      } else {
        // Cycle detected - pick arbitrary remaining node
        node = remaining.values().next().value!;
      }

      if (!remaining.has(node)) continue;

      order.push(node);
      remaining.delete(node);

      for (const edge of adjacency.get(node) ?? []) {
        if (remaining.has(edge.target)) {
          const newDeg = (indegree.get(edge.target) ?? 1) - 1;
          indegree.set(edge.target, newDeg);
          if (newDeg === 0) {
            queue.push(edge.target);
          }
        }
      }
    }

    return { order, cycles };
  }

  /**
   * Find all cycles using Tarjan's SCC algorithm.
   */
  private _findCycles(adjacency: Map<string, Edge[]>): string[][] {
    let indexCounter = 0;
    const stack: string[] = [];
    const lowlinks = new Map<string, number>();
    const index = new Map<string, number>();
    const onStack = new Set<string>();
    const sccs: string[][] = [];

    const strongconnect = (node: string): void => {
      index.set(node, indexCounter);
      lowlinks.set(node, indexCounter);
      indexCounter++;
      stack.push(node);
      onStack.add(node);

      for (const edge of adjacency.get(node) ?? []) {
        const neighbor = edge.target;
        if (!index.has(neighbor)) {
          strongconnect(neighbor);
          lowlinks.set(node, Math.min(lowlinks.get(node)!, lowlinks.get(neighbor)!));
        } else if (onStack.has(neighbor)) {
          lowlinks.set(node, Math.min(lowlinks.get(node)!, index.get(neighbor)!));
        }
      }

      if (lowlinks.get(node) === index.get(node)) {
        const scc: string[] = [];
        let w: string;
        do {
          w = stack.pop()!;
          onStack.delete(w);
          scc.push(w);
        } while (w !== node);

        if (scc.length > 1) {
          sccs.push(scc);
        } else if (scc.length === 1) {
          // Check for self-loop
          const edges = adjacency.get(scc[0]) ?? [];
          if (edges.some((e) => e.target === scc[0])) {
            sccs.push(scc);
          }
        }
      }
    };

    for (const node of this._nodes.keys()) {
      if (!index.has(node)) {
        strongconnect(node);
      }
    }

    return sccs;
  }
}
