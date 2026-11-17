// A node's settings, editable (rasl-w18). A line that reads one $variable or snippet
// parameter offers where to write a new value (rasl-6sr.7, owner 2026-11-16): at its
// definition (every use changes, or the @use argument) or only on this line.
import { type ReactElement, useEffect, useState } from "react";

import type { JsonSchema, SettingScope } from "../api";
import type { ViewNode, ViewSetting } from "../model";

export type SettingsEditorProps = {
  readonly node: ViewNode;
  readonly schema: JsonSchema | null;
  /** False when the node's own lines may not be edited (locked, removed, or editing off). */
  readonly editable: boolean;
  /** False when nothing may be edited: a $variable's or @use argument's definition neither. */
  readonly definitionsEditable: boolean;
  readonly onSet: (key: string, index: number, values: string, scope: SettingScope) => void;
  readonly onRemove: (key: string, index: number) => void;
  readonly onSetValues: (values: string) => void;
};

function definitionLabel(setting: ViewSetting): string {
  const d = setting.definition;
  if (!d) return "";
  return d.kind === "variable" ? `$${d.name} (${d.uses} use${d.uses === 1 ? "" : "s"})` : `@use argument $${d.name}`;
}

type SettingRowProps = {
  readonly setting: ViewSetting;
  readonly editable: boolean;
  readonly definitionsEditable: boolean;
  readonly onSet: (values: string, scope: SettingScope) => void;
  readonly onRemove: () => void;
};

function SettingRow({ setting, editable, definitionsEditable, onSet, onRemove }: SettingRowProps): ReactElement {
  const shown = setting.queued?.values ?? setting.values;
  const [value, setValue] = useState(shown);
  useEffect(() => setValue(shown), [shown]);
  const lineEditable = editable && setting.locked === null && !setting.removed;
  const definitionEditable =
    definitionsEditable && setting.definition !== null && setting.definition.locked === null && !setting.removed;
  const [scope, setScope] = useState<SettingScope>(definitionEditable ? "definition" : "line");
  const canSet =
    value.trim() !== "" && value.trim() !== shown && (scope === "line" ? lineEditable : definitionEditable);
  const title = setting.locked ? `This line ${setting.locked}` : undefined;

  return (
    <div className={`setting${setting.removed ? " removed" : ""}${setting.queued ? " queued" : ""}`}>
      <span className="setting-key mono" title={title}>
        {setting.key}
        {setting.index > 0 ? `[${setting.index}]` : ""}
      </span>
      <input
        className="input mono"
        value={value}
        aria-label={setting.key}
        disabled={!(lineEditable || definitionEditable)}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && canSet) onSet(value.trim(), scope);
        }}
        title={setting.hasBlock ? "Its block is kept as it is" : title}
      />
      <button className="button" disabled={!canSet} onClick={() => onSet(value.trim(), scope)}>
        Set
      </button>
      <button className="icon-button" title="Remove this line" disabled={!lineEditable} onClick={onRemove}>
        ×
      </button>
      {setting.written !== setting.values || setting.definition ? (
        <div className="setting-source small muted">
          written <span className="mono">{setting.written}</span>
          {setting.definition ? (
            <span className="scope">
              <label>
                <input
                  type="radio"
                  checked={scope === "definition"}
                  disabled={!definitionEditable}
                  onChange={() => setScope("definition")}
                />
                {definitionLabel(setting)}
              </label>
              <label title={lineEditable ? undefined : (title ?? "locked")}>
                <input
                  type="radio"
                  checked={scope === "line"}
                  disabled={!lineEditable}
                  onChange={() => setScope("line")}
                />
                only here
              </label>
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function SettingsEditor({
  node,
  schema,
  editable,
  definitionsEditable,
  onSet,
  onRemove,
  onSetValues,
}: SettingsEditorProps): ReactElement {
  const [newKey, setNewKey] = useState("");
  const [newValues, setNewValues] = useState("");
  const [values, setValues] = useState(node.values);
  useEffect(() => setValues(node.values), [node.values]);
  const present = new Set(node.settings.map((s) => s.key));
  const suggestions = Object.keys(schema?.properties ?? {}).filter(
    (key) => !present.has(key) && !["id", "type", "connect", "edge"].includes(key),
  );
  const add = (): void => {
    const key = newKey.trim();
    if (!key || !newValues.trim()) return;
    onSet(key, node.settings.filter((s) => s.key === key).length, newValues.trim(), "line");
    setNewKey("");
    setNewValues("");
  };

  return (
    <div className="settings">
      <div className="setting">
        <span className="setting-key mono" title="Values written after the node's id">
          (values)
        </span>
        <input
          className="input mono"
          value={values}
          placeholder="none"
          aria-label="values"
          disabled={!editable}
          onChange={(e) => setValues(e.target.value)}
        />
        <button
          className="button"
          disabled={!editable || values.trim() === node.values}
          onClick={() => onSetValues(values.trim())}
        >
          Set
        </button>
      </div>
      {node.settings.map((setting) => (
        <SettingRow
          key={`${setting.key}:${setting.index}`}
          setting={setting}
          editable={editable}
          definitionsEditable={definitionsEditable}
          onSet={(v, scope) => onSet(setting.key, setting.index, v, scope)}
          onRemove={() => onRemove(setting.key, setting.index)}
        />
      ))}
      {editable ? (
        <div className="setting add">
          <input
            className="input mono"
            list={`keys-${node.id}`}
            placeholder="setting"
            aria-label="new setting"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
          />
          <datalist id={`keys-${node.id}`}>
            {suggestions.map((key) => (
              <option key={key} value={key}>
                {schema?.properties?.[key]?.description ?? ""}
              </option>
            ))}
          </datalist>
          <input
            className="input mono"
            placeholder="values"
            aria-label="new setting values"
            value={newValues}
            onChange={(e) => setNewValues(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") add();
            }}
          />
          <button className="button" disabled={!newKey.trim() || !newValues.trim()} onClick={add}>
            Add
          </button>
        </div>
      ) : null}
    </div>
  );
}
