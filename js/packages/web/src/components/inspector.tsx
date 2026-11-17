// The selected node or connection: where it is written, its settings and ports, its metrics,
// and the edits that apply to it (rename, remove, disconnect).
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
    return (
      <div className="inspector">
        <div className="section-title">Connection</div>
        <div className="kv">
          <span>from</span>
          <span className="mono">{edge.source}</span>
          <span>into</span>
          <span className="mono">
            {edge.target}
            {edge.port ? `.${edge.port}` : ` (${edge.targetPort ?? "default"})`}
          </span>
          {edge.repeat !== null ? (
            <>
              <span>repeat</span>
              <span className="mono">{edge.repeat}</span>
            </>
          ) : null}
          {edge.repeatUntil !== null ? (
            <>
              <span>repeat_until</span>
              <span className="mono">{edge.repeatUntil}</span>
            </>
          ) : null}
          <span>written</span>
          <Place place={edge.place} />
        </div>
        {edge.locked ? <p className="muted">Locked: {edge.locked}.</p> : null}
        <button className="button danger" disabled={!canEdit} onClick={() => onDisconnect(edge)}>
          Disconnect
        </button>
      </div>
    );
  }
  if (!node)
    return (
      <div className="inspector muted">
        Select a node or a connection. Double-click the canvas, or drop a wire on it, to add a node.
      </div>
    );

  const canEdit = editable && node.locked === null && node.status !== "removed";
  return (
    <div className="inspector">
      <div className="section-title">{node.type}</div>
      <div className="kv">
        <span>id</span>
        <span className="rename">
          <input
            className="input mono"
            value={newId}
            disabled={!canEdit || node.status === "added"}
            onChange={(e) => setNewId(e.target.value)}
          />
          <button
            className="button"
            disabled={!canEdit || newId === node.id || newId === ""}
            onClick={() => onRename(node.id, newId)}
          >
            Rename
          </button>
        </span>
        <span>written</span>
        <Place place={node.place} />
      </div>
      {node.locked ? <p className="muted">Locked: {node.locked}.</p> : null}
      {node.error ? <p className="field-error">{node.error}</p> : null}
      {node.use ? (
        <div className="use-note">
          <span className="muted small">
            Made by <span className="mono">@use {node.use}</span>: its lines are the snippet&apos;s. Set a
            parameter&apos;s argument below, or detach it to edit every line.
          </span>
          <button className="button" disabled={!editable || node.status === "removed"} onClick={onDetach}>
            Detach
          </button>
        </div>
      ) : null}
      <div className="section-title">Settings</div>
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
          <div className="section-title">Metrics</div>
          <div className="kv">
            <span>pulls</span>
            <span className="mono">{metrics.handleCount}</span>
            <span>avg</span>
            <span className="mono">{metrics.avgExecutionTimeMs.toFixed(3)} ms</span>
            <span>success</span>
            <span className="mono">{(metrics.successRate * 100).toFixed(1)}%</span>
            {metrics.lastError ? (
              <>
                <span>last error</span>
                <span className="mono field-error">{metrics.lastError}</span>
              </>
            ) : null}
          </div>
        </>
      ) : null}
      <button className="button danger" disabled={!canEdit} onClick={() => onRemove(node.id)}>
        Remove node and its connections
      </button>
    </div>
  );
}
