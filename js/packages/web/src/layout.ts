// Automatic layout (owner, 2026-11-16: positions are not stored): ELK's layered algorithm,
// left to right, with each node's ports in a fixed order so wires do not cross needlessly.
import type { StagedGraph, ViewNode } from "./model";

export const NODE_WIDTH = 240;
const HEADER_HEIGHT = 46;
export const PORT_ROW = 22;

export function nodeHeight(node: ViewNode): number {
  return HEADER_HEIGHT + PORT_ROW * Math.max(node.inputs.length, node.outputs.length, 1) + 10;
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
      width: NODE_WIDTH,
      height: nodeHeight(node),
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
