// The palette: pick a node type, give it an id and settings, and see its ports before it is
// queued. Ports can depend on settings (an sACN source's universes), so they come from the
// server's previewNode, asked again as the settings change.
import { type ReactElement, useEffect, useMemo, useState } from "react";

import { type ConfigNode, type JsonSchema, type NodeType, previewNode, type Setting } from "../api";
import { nextId } from "../model";

export type AddNodeRequest = {
  readonly type: string;
  readonly id: string;
  readonly values: string;
  readonly settings: readonly Setting[];
  readonly preview: ConfigNode;
};

export type AddNodeDialogProps = {
  readonly types: readonly NodeType[];
  readonly takenIds: ReadonlySet<string>;
  /** Set when the dialog was opened by dropping a wire: the new node is connected to it. */
  readonly from: { readonly node: string; readonly port: string } | null;
  readonly onAdd: (request: AddNodeRequest) => void;
  readonly onClose: () => void;
};

const HIDDEN_FIELDS = new Set(["id", "type", "connect", "edge"]);

function fields(schema: JsonSchema | null): readonly [string, JsonSchema][] {
  return Object.entries(schema?.properties ?? {}).filter(([key]) => !HIDDEN_FIELDS.has(key));
}

export function AddNodeDialog({ types, takenIds, from, onAdd, onClose }: AddNodeDialogProps): ReactElement {
  const [search, setSearch] = useState("");
  const [type, setType] = useState<NodeType | null>(null);
  const [id, setId] = useState("");
  const [values, setValues] = useState("");
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<ConfigNode | null>(null);

  const matches = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return types.filter(
      (t) =>
        needle === "" ||
        t.name.toLowerCase().includes(needle) ||
        t.aliases.some((a) => a.toLowerCase().includes(needle)) ||
        t.summary.toLowerCase().includes(needle),
    );
  }, [types, search]);

  const filled: readonly Setting[] = useMemo(
    () =>
      Object.entries(settings)
        .filter(([, v]) => v.trim() !== "")
        .map(([key, v]) => ({ key, values: v.trim() })),
    [settings],
  );

  useEffect(() => {
    if (!type) return undefined;
    const timer = window.setTimeout(() => {
      previewNode(type.name, values.trim(), filled).then(setPreview, (e: unknown) =>
        setPreview({
          id,
          type: type.name,
          place: { path: "", line: 0 },
          locked: null,
          settings: [],
          inputs: [],
          outputs: [],
          error: String(e),
        }),
      );
    }, 250);
    return () => window.clearTimeout(timer);
  }, [type, values, filled, id]);

  const choose = (chosen: NodeType): void => {
    setType(chosen);
    setId(nextId(chosen.name, takenIds));
    setSettings({});
    setValues("");
    setPreview(null);
  };

  const idProblem = !/^[A-Za-z_][A-Za-z0-9_]*$/.test(id)
    ? "letters, digits and _, not first a digit"
    : takenIds.has(id)
      ? "already taken"
      : null;
  const canAdd = type !== null && preview !== null && idProblem === null;

  return (
    <div className="dialog-backdrop" onMouseDown={onClose}>
      <div className="dialog" onMouseDown={(e) => e.stopPropagation()} role="dialog" aria-label="Add a node">
        <div className="dialog-title">
          {type ? `New ${type.name}` : "Add a node"}
          {from ? (
            <span className="muted">
              {" "}
              fed by {from.node}.{from.port}
            </span>
          ) : null}
        </div>
        {type === null ? (
          <>
            <input
              autoFocus
              className="input"
              placeholder="Search node types"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <ul className="type-list">
              {matches.map((t) => (
                <li key={t.name}>
                  <button className="type-item" onClick={() => choose(t)}>
                    <span className="type-name">{t.name}</span>
                    <span className="muted">{t.summary}</span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <div className="add-form">
            <label className="field">
              <span>id</span>
              <input autoFocus className="input mono" value={id} onChange={(e) => setId(e.target.value)} />
              {idProblem ? <span className="field-error">{idProblem}</span> : null}
            </label>
            <label className="field">
              <span title="Values written after the id on the node line, as config text">values</span>
              <input
                className="input mono"
                placeholder="(none)"
                value={values}
                onChange={(e) => setValues(e.target.value)}
              />
            </label>
            {fields(type.schema).map(([key, schema]) => (
              <label className="field" key={key} title={schema.description}>
                <span>{key}</span>
                <input
                  className="input mono"
                  placeholder={
                    schema.default === undefined || schema.default === null ? "" : JSON.stringify(schema.default)
                  }
                  value={settings[key] ?? ""}
                  onChange={(e) => setSettings({ ...settings, [key]: e.target.value })}
                />
              </label>
            ))}
            <div className="preview">
              {preview === null ? (
                <span className="muted">Building…</span>
              ) : preview.error ? (
                <span className="field-error">{preview.error}</span>
              ) : (
                <span className="muted">
                  in: {preview.inputs.map((p) => p.name).join(", ") || "none"} · out:{" "}
                  {preview.outputs.map((p) => p.name).join(", ") || "none"}
                </span>
              )}
            </div>
            <div className="dialog-actions">
              <button className="button" onClick={() => setType(null)}>
                Back
              </button>
              <button
                className="button primary"
                disabled={!canAdd}
                onClick={() =>
                  preview && onAdd({ type: type.name, id, values: values.trim(), settings: filled, preview })
                }
              >
                Queue
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
