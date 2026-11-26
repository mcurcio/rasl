// Automatic layout (owner, 2026-11-16: positions are not stored): ELK's layered algorithm,
// left to right, with each node's ports in a fixed order so wires do not cross needlessly.
// Each node is sized by patchbay's NodeBox geometry, the same formula the card is drawn to.
import { type NodeBoxShape, nodeBoxSize } from "@mcurcio/patchbay/graph";

import type { StagedGraph, ViewNode } from "./model";

/**
 * A node card's ports: NodeBox's default, the inputs' rows and then the outputs', each row the card's full width. Side
 * by side, each column is half of it, and NodeBox keeps a port's whole type and cuts its name, which rasl's long types
 * ("matrix|color") cut to a letter.
 */
export const NODE_PORTS = "stacked";

/** What decides a node card's size: its ports, and whether it has an error line and a locked footer. */
export function nodeShape(node: ViewNode): NodeBoxShape {
  return {
    inputs: node.inputs.length,
    outputs: node.outputs.length,
    ports: NODE_PORTS,
    line: node.error !== null,
    footer: node.locked !== null,
  };
}

export type Positions = ReadonlyMap<string, { readonly x: number; readonly y: number }>;

type Elk = { layout: (graph: object) => Promise<{ children?: { id: string; x?: number; y?: number }[] }> };
let elk: Promise<Elk> | undefined;

/** ELK is large: loaded on first use, in its own chunk. */
function getElk(): Promise<Elk> {
  elk ??= import("elkjs/lib/elk.bundled.js").then(({ default: ELK }) => new ELK() as Elk);
  return elk;
}

export async function layout(graph: StagedGraph): Promise<Positions> {
  const engine = await getElk();
  const ids = new Set(graph.nodes.map((n) => n.id));
  const result = await engine.layout({
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "RIGHT",
      "elk.layered.spacing.nodeNodeBetweenLayers": "90",
      "elk.spacing.nodeNode": "40",
      "elk.portConstraints": "FIXED_ORDER",
    },
    children: graph.nodes.map((node) => ({
      id: node.id,
      ...nodeBoxSize(nodeShape(node)),
      ports: [
        ...node.inputs.map((p, i) => ({
          id: `${node.id}:in:${p.name}`,
          layoutOptions: { "elk.port.side": "WEST", "elk.port.index": String(i) },
        })),
        ...node.outputs.map((p, i) => ({
          id: `${node.id}:out:${p.name}`,
          layoutOptions: { "elk.port.side": "EAST", "elk.port.index": String(i) },
        })),
      ],
    })),
    edges: graph.edges
      .filter((e) => e.sourceNode !== null && ids.has(e.sourceNode) && ids.has(e.target))
      .map((e) => ({
        id: e.key,
        sources: [e.sourcePort ? `${e.sourceNode}:out:${e.sourcePort}` : (e.sourceNode as string)],
        targets: [e.targetPort ? `${e.target}:in:${e.targetPort}` : e.target],
      })),
  });
  const positions = new Map<string, { x: number; y: number }>();
  for (const child of result.children ?? []) positions.set(child.id, { x: child.x ?? 0, y: child.y ?? 0 });
  return positions;
}
