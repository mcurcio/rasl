// A node on the canvas, drawn by patchbay's NodeBox: its id the title, its type the subtitle, its health from live
// metrics a Pill, a queued change the box's change, a build error its line, and a locked node's Badge in the footer.
// Each port is a PortRow with the editor's own handle ids (in:<name>, out:<name>), which edits and ELK's ports use.
// The line and the footer are drawn exactly when layout.ts's nodeShape() makes room for them.
import { NodeBox, type PortHint, type PortSpec } from "@mcurcio/patchbay/graph";
import { Badge, Pill, type PillTone } from "@mcurcio/patchbay/primitives";
import type { NodeProps } from "@xyflow/react";
import type { ReactElement } from "react";

import type { NodeMetrics, Port } from "../api";
import { NODE_PORTS } from "../layout";
import type { ViewNode } from "../model";

export type NodeCardData = {
  readonly node: ViewNode;
  readonly metrics: NodeMetrics | undefined;
  /** The ports a refused connection names, by handle id, with the refusal's words. */
  readonly problemPorts: ReadonlyMap<string, string>;
  /** While a wire is dragged: for each handle on the other side, whether it takes the wire. */
  readonly hints: ReadonlyMap<string, boolean> | null;
};

type Health = "idle" | "ok" | "degraded" | "failing";

const HEALTH_TONES: Readonly<Record<Health, PillTone>> = {
  idle: "off",
  ok: "ok",
  degraded: "warn",
  failing: "err",
};

function health(metrics: NodeMetrics | undefined): Health {
  if (!metrics) return "idle";
  if (metrics.lastError) return "failing";
  return metrics.successRate >= 0.99 ? "ok" : "degraded";
}

/** A port's type as the card shows it: its payload types, its component count, and a fixed connection count. */
function typeLabel(port: Port): string {
  const type = port.types.join("|");
  const count = port.minCount !== null && port.minCount === port.maxCount ? `×${port.minCount}` : "";
  const width = port.components !== null ? `[${port.components}]` : "";
  return `${type}${width}${count}`;
}

function hint(handle: string, hints: ReadonlyMap<string, boolean> | null): PortHint | undefined {
  const takes = hints?.get(handle);
  return takes === undefined ? undefined : takes ? "ok" : "no";
}

export function NodeCard({ data, selected }: NodeProps & { data: NodeCardData }): ReactElement {
  const { node, metrics, problemPorts, hints } = data;
  const port = (side: "in" | "out", p: Port): PortSpec => {
    const id = `${side}:${p.name}`;
    return { id, label: p.name, typeLabel: typeLabel(p), hint: hint(id, hints), problem: problemPorts.get(id) };
  };
  const state = health(metrics);
  return (
    <NodeBox
      title={node.id}
      subtitle={node.type}
      selected={selected}
      change={node.status === "saved" ? undefined : node.status}
      failed={node.error !== null}
      line={node.error ?? undefined}
      status={<Pill tone={HEALTH_TONES[state]} label={state} title={metrics?.lastError ?? undefined} />}
      inputs={node.inputs.map((p) => port("in", p))}
      outputs={node.outputs.map((p) => port("out", p))}
      ports={NODE_PORTS}
      footer={
        node.locked !== null ? (
          <Badge tone="muted" title={node.locked}>
            locked
          </Badge>
        ) : undefined
      }
    />
  );
}
