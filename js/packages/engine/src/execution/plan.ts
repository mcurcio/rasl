/**
 * ExecutionPlan - Compiled graph ready for runtime execution.
 */

import type { INode } from "../nodes/index.js";

import type { Edge } from "./edge.js";

/**
 * Description of a node for serialization.
 */
export interface INodeDescription {
  id: string;
  type: string;
  inputs: readonly string[];
  outputs: readonly string[];
}

/**
 * Description of an edge for serialization.
 */
export interface IEdgeDescription {
  source: string;
  sourcePort: string;
  target: string;
  targetPort: string;
}

/**
 * Complete graph description for serialization.
 */
export interface IGraphDescription {
  nodes: INodeDescription[];
  edges: IEdgeDescription[];
  topologicalOrder: string[];
}

/**
 * Compiled graph ready for runtime execution.
 *
 * Contains all information needed by the scheduler to execute the graph:
 * nodes, their connections, and execution order.
 */
export class ExecutionPlan {
  /**
   * Map of node ID to Node instance.
   */
  readonly nodes: Map<string, INode>;

  /**
   * Map of source node ID to list of outgoing Edges.
   */
  readonly adjacency: Map<string, Edge[]>;

  /**
   * Node IDs in valid execution order (sources first, sinks last).
   */
  readonly topologicalOrder: readonly string[];

  constructor(nodes: Map<string, INode>, adjacency: Map<string, Edge[]>, topologicalOrder: string[]) {
    this.nodes = nodes;
    this.adjacency = adjacency;
    this.topologicalOrder = Object.freeze([...topologicalOrder]);
  }

  /**
   * Serialize the execution plan to a JSON-compatible object.
   */
  describe(): IGraphDescription {
    const nodes: INodeDescription[] = [];

    for (const nodeId of this.topologicalOrder) {
      const node = this.nodes.get(nodeId);
      if (!node) continue;

      const inputs = node.inputs?.names ?? [];
      const outputs = node.outputs?.names ?? [];

      nodes.push({
        id: node.id,
        type: node.constructor.name,
        inputs,
        outputs,
      });
    }

    const edges: IEdgeDescription[] = [];
    for (const [_sourceId, edgeList] of this.adjacency) {
      for (const edge of edgeList) {
        edges.push({
          source: edge.source,
          sourcePort: edge.sourcePort,
          target: edge.target,
          targetPort: edge.targetPort,
        });
      }
    }

    return {
      nodes,
      edges,
      topologicalOrder: [...this.topologicalOrder],
    };
  }
}
