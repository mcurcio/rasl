// The palette: pick a node type, give it an id and settings, and see its ports before it is
// queued. Ports can depend on settings (an sACN source's universes), so they come from the
// server's previewNode, asked again as the settings change. Drawn on patchbay's Dialog (Escape,
// the Close button and a press outside close it; focus stays inside and returns after), with
// Field, TextInput and Button.
import { Button, Dialog, Field, TextInput } from "@mcurcio/patchbay/primitives";
import { type ReactElement, useEffect, useMemo, useRef, useState } from "react";

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
  // The step's first field takes focus: the search, or the new node's id. Set here rather than by autoFocus, which
  // would take focus before the Dialog notes where it came from, and so where to return it.
  const searchRef = useRef<HTMLInputElement>(null);
  const idRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    (type === null ? searchRef : idRef).current?.focus();
  }, [type]);

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
          values: "",
          use: null,
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
    <Dialog
      open
      onClose={onClose}
      title={
        <>
          {type ? `New ${type.name}` : "Add a node"}
          {from ? (
            <span className="muted">
              {" "}
              fed by {from.node}.{from.port}
            </span>
          ) : null}
        </>
      }
      actions={
        type === null ? undefined : (
          <>
            <Button onClick={() => setType(null)}>Back</Button>
            <Button
              tone="primary"
              disabled={!canAdd}
              onClick={() =>
                preview && onAdd({ type: type.name, id, values: values.trim(), settings: filled, preview })
              }
            >
              Queue
            </Button>
          </>
        )
      }
    >
      {type === null ? (
        <>
          <TextInput
            ref={searchRef}
            aria-label="Search node types"
            placeholder="Search node types"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <ul className="type-list">
            {matches.map((t) => (
              <li key={t.name}>
                <button type="button" className="type-item" onClick={() => choose(t)}>
                  <span className="type-name">{t.name}</span>
                  <span className="muted">{t.summary}</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <div className="add-form">
          <Field label="id" layout="inline" error={idProblem ?? undefined}>
            <TextInput ref={idRef} font="code" value={id} onChange={(e) => setId(e.target.value)} />
          </Field>
          <Field
            label={<span title="Values written after the id on the node line, as config text">values</span>}
            layout="inline"
          >
            <TextInput font="code" placeholder="(none)" value={values} onChange={(e) => setValues(e.target.value)} />
          </Field>
          {fields(type.schema).map(([key, schema]) => (
            <Field label={key} layout="inline" key={key} title={schema.description}>
              <TextInput
                font="code"
                placeholder={
                  schema.default === undefined || schema.default === null ? "" : JSON.stringify(schema.default)
                }
                value={settings[key] ?? ""}
                onChange={(e) => setSettings({ ...settings, [key]: e.target.value })}
              />
            </Field>
          ))}
          <div className="preview" role="status">
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
        </div>
      )}
    </Dialog>
  );
}
