// The selected node or connection: where it is written, its settings and ports, its metrics,
// and the edits that apply to it (rename, remove, disconnect, and connecting each port from the
// keyboard: a "Connect to" Select per port, listing the ports the canvas's one rule accepts, from
// patchbay's connectTargets in app.tsx). Drawn on patchbay's SectionTitle, KeyValue, TextInput,
// Select and Button. It is the body of the side column, whose one header row AppShell
// draws from inspectorTitle(): a Panel's on a wide window, the sheet's own on a narrow one.
import { Button, KeyValue, type KeyValueRow, SectionTitle, Select, TextInput } from "@mcurcio/patchbay/primitives";
import { type ReactElement, useEffect, useState } from "react";

import type { JsonSchema, NodeMetrics, SettingScope } from "../api";
import type { ViewEdge, ViewNode } from "../model";
import { SettingsEditor } from "./settings-editor";

export type InspectorProps = {
  readonly node: ViewNode | null;
  readonly edge: ViewEdge | null;
  readonly metrics: NodeMetrics | undefined;
  readonly editable: boolean;
  readonly onRename: (id: string, newId: string) => void;
  readonly onRemove: (id: string) => void;
  readonly onDisconnect: (edge: ViewEdge) => void;
  /** The ports one of the node's ports may be wired to, by the canvas's rule: each choice's value and words. */
  readonly connectTargets: (side: PortSide, port: string) => readonly ConnectChoice[];
  /** Wire one of the node's ports to the choice `value`, as a drop on the canvas would. */
  readonly onConnectTo: (side: PortSide, port: string, value: string) => void;
  readonly schema: JsonSchema | null;
  readonly onSetSetting: (key: string, index: number, values: string, scope: SettingScope) => void;
  readonly onRemoveSetting: (key: string, index: number) => void;
  readonly onSetValues: (values: string) => void;
  readonly onDetach: () => void;
};

export type PortSide = "input" | "output";

export type ConnectChoice = { readonly value: string; readonly label: string };

/**
 * A port's "Connect to" choice, the keyboard's way to wire it (patchbay's U2): the ports on the other side that take
 * it, or that it takes. Choosing one queues the connection, and the choice goes back to its prompt.
 */
function PortConnect({
  side,
  name,
  choices,
  disabled,
  onChoose,
}: {
  readonly side: PortSide;
  readonly name: string;
  readonly choices: readonly ConnectChoice[];
  readonly disabled: boolean;
  readonly onChoose: (value: string) => void;
}): ReactElement {
  return (
    <div className="port-connect" role="group" aria-label={`${side} ${name}`}>
      <span className="port-connect-name mono">{name}</span>
      <span className="muted small">{side === "input" ? "in" : "out"}</span>
      <Select
        className="port-connect-select"
        font="code"
        aria-label={`Connect ${side} ${name} to`}
        value=""
        disabled={disabled || choices.length === 0}
        onChange={(e) => {
          if (e.target.value !== "") onChoose(e.target.value);
        }}
      >
        <option value="">{choices.length === 0 ? "No port takes it" : "Connect to…"}</option>
        {choices.map((choice) => (
          <option key={choice.value} value={choice.value}>
            {choice.label}
          </option>
        ))}
      </Select>
    </div>
  );
}

/** The side column's title: the selected connection's or node's (its type), or the column's name with no selection. */
export function inspectorTitle(node: ViewNode | null, edge: ViewEdge | null): string {
  if (edge) return "Connection";
  return node ? node.type : "Side panel";
}

function Place({ place }: { readonly place: { readonly path: string; readonly line: number } | null }): ReactElement {
  return <span className="mono muted">{place ? `${place.path.split("/").pop()}:${place.line}` : "not saved yet"}</span>;
}

function mono(value: string | number): ReactElement {
  return <span className="mono">{value}</span>;
}

export function Inspector({
  node,
  edge,
  metrics,
  editable,
  onRename,
  onRemove,
  onDisconnect,
  connectTargets,
  onConnectTo,
  schema,
  onSetSetting,
  onRemoveSetting,
  onSetValues,
  onDetach,
}: InspectorProps): ReactElement {
  const [newId, setNewId] = useState(node?.id ?? "");
  useEffect(() => setNewId(node?.id ?? ""), [node?.id]);

  if (edge) {
    const canEdit = editable && edge.locked === null && edge.status !== "removed";
    const rows: KeyValueRow[] = [
      { key: "from", value: mono(edge.source) },
      {
        key: "into",
        value: mono(`${edge.target}${edge.port ? `.${edge.port}` : ` (${edge.targetPort ?? "default"})`}`),
      },
    ];
    if (edge.repeat !== null) rows.push({ key: "repeat", value: mono(edge.repeat) });
    if (edge.repeatUntil !== null) rows.push({ key: "repeat_until", value: mono(edge.repeatUntil) });
    rows.push({ key: "written", value: <Place place={edge.place} /> });
    return (
      <div className="inspector">
        <KeyValue className="inspector-kv" rows={rows} />
        {edge.locked ? <p className="muted">Locked: {edge.locked}.</p> : null}
        <Button className="inspector-action" tone="danger" disabled={!canEdit} onClick={() => onDisconnect(edge)}>
          Disconnect
        </Button>
      </div>
    );
  }
  if (!node)
    return (
      <div className="inspector">
        <p className="muted">
          Select a node or a connection. Double-click the canvas, or drop a wire on it, to add a node.
        </p>
      </div>
    );

  const canEdit = editable && node.locked === null && node.status !== "removed";
  const metricRows: KeyValueRow[] = metrics
    ? [
        { key: "pulls", value: mono(metrics.handleCount) },
        { key: "avg", value: mono(`${metrics.avgExecutionTimeMs.toFixed(3)} ms`) },
        { key: "success", value: mono(`${(metrics.successRate * 100).toFixed(1)}%`) },
        ...(metrics.lastError ? [{ key: "last error", value: mono(metrics.lastError), tone: "err" }] : []),
      ]
    : [];
  return (
    <div className="inspector">
      <KeyValue
        className="inspector-kv"
        rows={[
          {
            key: "id",
            value: (
              <span className="rename">
                <TextInput
                  className="rename-input"
                  font="code"
                  aria-label="id"
                  value={newId}
                  disabled={!canEdit || node.status === "added"}
                  onChange={(e) => setNewId(e.target.value)}
                />
                <Button
                  disabled={!canEdit || newId === node.id || newId === ""}
                  onClick={() => onRename(node.id, newId)}
                >
                  Rename
                </Button>
              </span>
            ),
          },
          { key: "written", value: <Place place={node.place} /> },
        ]}
      />
      {node.locked ? <p className="muted">Locked: {node.locked}.</p> : null}
      {node.error ? <p className="field-error">{node.error}</p> : null}
      {node.use ? (
        <div className="use-note" role="note">
          <span className="muted small">
            Made by <span className="mono">@use {node.use}</span>: its lines are the snippet&apos;s. Set a
            parameter&apos;s argument below, or detach it to edit every line.
          </span>
          <Button disabled={!editable || node.status === "removed"} onClick={onDetach}>
            Detach
          </Button>
        </div>
      ) : null}
      <SectionTitle>Settings</SectionTitle>
      <SettingsEditor
        node={node}
        schema={schema}
        editable={canEdit}
        definitionsEditable={editable && node.status !== "removed"}
        onSet={onSetSetting}
        onRemove={onRemoveSetting}
        onSetValues={onSetValues}
      />
      {node.inputs.length + node.outputs.length > 0 ? (
        <>
          <SectionTitle>Ports</SectionTitle>
          <div className="ports">
            {[
              ...node.inputs.map((p) => ["input", p.name] as const),
              ...node.outputs.map((p) => ["output", p.name] as const),
            ].map(([side, name]) => (
              <PortConnect
                key={`${side}:${name}`}
                side={side}
                name={name}
                choices={canEdit ? connectTargets(side, name) : []}
                disabled={!canEdit}
                onChoose={(value) => onConnectTo(side, name, value)}
              />
            ))}
          </div>
        </>
      ) : null}
      {metrics ? (
        <>
          <SectionTitle>Metrics</SectionTitle>
          <KeyValue className="inspector-kv" rows={metricRows} />
        </>
      ) : null}
      <Button className="inspector-action" tone="danger" disabled={!canEdit} onClick={() => onRemove(node.id)}>
        Remove node and its connections
      </Button>
    </div>
  );
}
