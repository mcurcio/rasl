// A node on the canvas: its id and type, health from live metrics, and a handle per port.
// Its locked and change badges are patchbay's Badge, in the change tones.
import { Badge } from "@mcurcio/patchbay/primitives";
import { Handle, type NodeProps, Position } from "@xyflow/react";
import type { ReactElement } from "react";

import type { NodeMetrics, Port } from "../api";
import { NODE_WIDTH, PORT_ROW } from "../layout";
import type { ViewNode } from "../model";

export type NodeCardData = {
  readonly node: ViewNode;
  readonly metrics: NodeMetrics | undefined;
  readonly problemPorts: ReadonlySet<string>;
  /** While a wire is dragged: for each handle on the other side, whether it takes the wire. */
  readonly hints: ReadonlyMap<string, boolean> | null;
};

function handleClass(
  handle: string,
  problems: ReadonlySet<string>,
  hints: ReadonlyMap<string, boolean> | null,
): string {
  const classes = [];
  if (problems.has(handle)) classes.push("handle-problem");
  const hint = hints?.get(handle);
  if (hint === true) classes.push("hint-ok");
  if (hint === false) classes.push("hint-no");
  return classes.join(" ");
}

function health(metrics: NodeMetrics | undefined): string {
  if (!metrics) return "idle";
  if (metrics.lastError) return "failing";
  return metrics.successRate >= 0.99 ? "ok" : "degraded";
}

function portLabel(port: Port): string {
  const type = port.types.join("|");
  const count = port.minCount !== null && port.minCount === port.maxCount ? `×${port.minCount}` : "";
  const width = port.components !== null ? `[${port.components}]` : "";
  return `${type}${width}${count}`;
}

export function NodeCard({ data, selected }: NodeProps & { data: NodeCardData }): ReactElement {
  const { node, metrics, problemPorts, hints } = data;
  const rows = Math.max(node.inputs.length, node.outputs.length, 1);
  return (
    <div
      className={`node-card status-${node.status}${selected ? " selected" : ""}${node.error ? " has-error" : ""}`}
      style={{ width: NODE_WIDTH }}
      title={node.error ?? node.locked ?? undefined}
    >
      <div className="node-header">
        <span className={`health health-${health(metrics)}`} title={metrics?.lastError ?? health(metrics)} />
        <span className="node-id">{node.id}</span>
        <span className="node-type">{node.type}</span>
        {node.locked ? (
          <Badge tone="muted" title={node.locked}>
            locked
          </Badge>
        ) : null}
        {node.status !== "saved" ? <Badge tone={node.status}>{node.status}</Badge> : null}
      </div>
      <div className="node-ports" style={{ height: rows * PORT_ROW }}>
        {node.inputs.map((port, i) => (
          <div key={`in:${port.name}`} className="port port-in" style={{ top: i * PORT_ROW }}>
            <Handle
              id={`in:${port.name}`}
              type="target"
              position={Position.Left}
              className={handleClass(`in:${port.name}`, problemPorts, hints)}
            />
            <span className="port-name">{port.name}</span>
            <span className="port-type">{portLabel(port)}</span>
          </div>
        ))}
        {node.outputs.map((port, i) => (
          <div key={`out:${port.name}`} className="port port-out" style={{ top: i * PORT_ROW }}>
            <span className="port-type">{portLabel(port)}</span>
            <span className="port-name">{port.name}</span>
            <Handle
              id={`out:${port.name}`}
              type="source"
              position={Position.Right}
              className={handleClass(`out:${port.name}`, problemPorts, hints)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
