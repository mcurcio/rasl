// The selected node or connection: where it is written, its settings and ports, its metrics,
// and the edits that apply to it (rename, remove, disconnect). Drawn on patchbay's Panel,
// SectionTitle, KeyValue, TextInput and Button.
import { Button, KeyValue, type KeyValueRow, Panel, SectionTitle, TextInput } from "@mcurcio/patchbay/primitives";
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
  readonly schema: JsonSchema | null;
  readonly onSetSetting: (key: string, index: number, values: string, scope: SettingScope) => void;
  readonly onRemoveSetting: (key: string, index: number) => void;
  readonly onSetValues: (values: string) => void;
  readonly onDetach: () => void;
};

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
      <Panel className="inspector" title="Connection">
        <KeyValue className="inspector-kv" rows={rows} />
        {edge.locked ? <p className="muted">Locked: {edge.locked}.</p> : null}
        <Button className="inspector-action" tone="danger" disabled={!canEdit} onClick={() => onDisconnect(edge)}>
          Disconnect
        </Button>
      </Panel>
    );
  }
  if (!node)
    return (
      <Panel className="inspector" aria-label="Inspector">
        <p className="muted">
          Select a node or a connection. Double-click the canvas, or drop a wire on it, to add a node.
        </p>
      </Panel>
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
    <Panel className="inspector" title={node.type}>
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
      {metrics ? (
        <>
          <SectionTitle>Metrics</SectionTitle>
          <KeyValue className="inspector-kv" rows={metricRows} />
        </>
      ) : null}
      <Button className="inspector-action" tone="danger" disabled={!canEdit} onClick={() => onRemove(node.id)}>
        Remove node and its connections
      </Button>
    </Panel>
  );
}
